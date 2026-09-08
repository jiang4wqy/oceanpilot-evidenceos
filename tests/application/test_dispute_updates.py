import asyncio
import base64
import json
import sqlite3
from datetime import UTC, datetime
from threading import Event
from time import monotonic
from uuid import uuid4

import pytest

from oceanpilot.adapters.persistence.dispute_agent import SQLiteDisputeAgentStore
from oceanpilot.adapters.persistence.dispute_updates import SQLiteDisputeUpdateReader
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.dispute_agent import DisputeAgentService
from oceanpilot.application.dispute_updates import DisputeUpdatesService
from oceanpilot.application.disputes import DisputeService
from oceanpilot.domain.dispute import DisputeError

OP = {"role": "OPERATOR", "actor_id": "sync-operator"}
MERCHANT = {"role": "MERCHANT", "actor_id": "sync-merchant", "merchant_id": "sync-merchant-a"}
OTHER = {"role": "MERCHANT", "actor_id": "sync-other", "merchant_id": "sync-merchant-b"}
AGENT = {"role": "AGENT", "actor_id": "sync-agent"}
NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)


@pytest.fixture
def stack(tmp_path):
    path = tmp_path / "updates.db"
    disputes = DisputeService(SQLiteDisputeStore(path), clock=lambda: NOW)
    agent = DisputeAgentService(SQLiteDisputeAgentStore(path), disputes, clock=lambda: NOW)
    updates = DisputeUpdatesService(SQLiteDisputeUpdateReader(path), poll_interval=0.015)
    return disputes, agent, updates, path


def intake(disputes, merchant=MERCHANT["merchant_id"]):
    return disputes.execute(
        {
            "command_id": str(uuid4()),
            "action": "INTAKE",
            "confirmed": True,
            "data": {
                "merchant_id": merchant,
                "transaction_id": "sync-transaction",
                "scheme": "VISA",
                "channel": "MOCK",
                "reason_code": "13.1",
                "amount_minor": 12500,
                "currency": "USD",
                "event_id": str(uuid4()),
            },
        },
        OP,
    )["case"]


def comment(disputes, case):
    return disputes.execute(
        {
            "command_id": str(uuid4()),
            "action": "COMMENT",
            "confirmed": False,
            "case_id": case["id"],
            "expected_revision": case["revision"],
            "data": {"message": "新的共享案件事实"},
        },
        OP,
    )["case"]


def poll(updates, identity=OP, **kwargs):
    return asyncio.run(updates.poll(identity, timeout=kwargs.pop("timeout", 0), **kwargs))


def test_initial_scope_baseline_and_repeat_cursor_are_read_only(stack):
    disputes, agent, updates, path = stack
    own, other = intake(disputes), intake(disputes, OTHER["merchant_id"])
    agent.observe(own, "INTAKE")
    with sqlite3.connect(path) as connection:
        tables = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        before = {
            name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in tables
        }
    baseline = poll(updates, MERCHANT)
    assert baseline["changed_case_ids"] == [own["id"]]
    assert other["id"] not in json.dumps(baseline)
    assert baseline["reset"] is True
    unchanged = poll(updates, MERCHANT, cursor=baseline["cursor"])
    assert unchanged == {
        "cursor": baseline["cursor"],
        "changed_case_ids": [],
        "changes": [],
        "reset": False,
        "timed_out": True,
    }
    with sqlite3.connect(path) as connection:
        after = {
            name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in tables
        }
    assert before == after


def test_case_command_from_another_store_wakes_both_clients_without_memory_bus(stack):
    disputes, _, updates, path = stack
    case = intake(disputes)

    async def scenario():
        merchant = await updates.poll(MERCHANT, case_id=case["id"], timeout=0)
        operations = await updates.poll(OP, timeout=0)
        merchant_wait = asyncio.create_task(
            updates.poll(
                MERCHANT,
                case_id=case["id"],
                cursor=merchant["cursor"],
                timeout=2,
            )
        )
        operations_wait = asyncio.create_task(
            updates.poll(OP, cursor=operations["cursor"], timeout=2)
        )
        await asyncio.sleep(0.04)
        independent = DisputeService(SQLiteDisputeStore(path), clock=lambda: NOW)
        changed = await asyncio.to_thread(comment, independent, case)
        results = await asyncio.gather(merchant_wait, operations_wait)
        for result in results:
            assert result["changed_case_ids"] == [case["id"]]
            assert result["changes"][0]["revision"] == changed["revision"]
            assert result["changes"][0]["case_changed"] is True
            assert result["timed_out"] is False

    start = monotonic()
    asyncio.run(scenario())
    assert monotonic() - start < 1


def test_new_agent_run_wakes_both_audiences_without_case_revision_change(stack):
    disputes, agent, updates, _ = stack
    case = intake(disputes)
    cursors = {
        identity["role"]: poll(updates, identity, case_id=case["id"])["cursor"]
        for identity in (OP, MERCHANT)
    }
    agent.observe(case, "MANUAL_RUN")
    for identity in (OP, MERCHANT):
        result = poll(updates, identity, case_id=case["id"], cursor=cursors[identity["role"]])
        assert result["changes"] == [
            {
                "case_id": case["id"],
                "revision": 1,
                "case_changed": False,
                "agent_changed": True,
                "conversation_changed": False,
            }
        ]


def test_private_conversation_only_wakes_its_own_audience(stack):
    disputes, agent, updates, _ = stack
    case = intake(disputes)
    agent.observe(case, "INTAKE")
    op_cursor = poll(updates, OP)["cursor"]
    merchant_cursor = poll(updates, MERCHANT)["cursor"]
    agent.converse(case["id"], MERCHANT, "商户私有 AI 问题", 1)
    unchanged = poll(updates, OP, cursor=op_cursor)
    assert unchanged["cursor"] == op_cursor
    assert unchanged["changes"] == []
    merchant_change = poll(updates, MERCHANT, cursor=merchant_cursor)
    assert merchant_change["changes"][0]["conversation_changed"] is True
    assert merchant_change["changes"][0]["case_changed"] is False
    assert "商户私有" not in json.dumps(merchant_change)
    agent.converse(case["id"], OP, "运营私有 AI 问题", 1)
    unchanged = poll(updates, MERCHANT, cursor=merchant_change["cursor"])
    assert unchanged["changes"] == []
    assert poll(updates, OP, cursor=op_cursor)["changes"][0]["conversation_changed"] is True


def test_completed_background_analysis_notifies_only_its_target_audience(stack):
    disputes, agent, updates, _ = stack
    case = intake(disputes)
    agent.observe(case, "INTAKE")
    op_cursor = poll(updates, OP)["cursor"]
    merchant_cursor = poll(updates, MERCHANT)["cursor"]
    agent.converse(
        case["id"], AGENT, "面向商户的自动分析", 1, trigger="AUTO_EVENT:INTAKE", audience="MERCHANT"
    )
    assert poll(updates, OP, cursor=op_cursor)["changes"] == []
    assert (
        poll(updates, MERCHANT, cursor=merchant_cursor)["changes"][0]["conversation_changed"]
        is True
    )


def test_foreign_merchant_changes_do_not_wake_even_an_empty_merchant_queue(stack):
    disputes, _, updates, _ = stack
    cursor = poll(updates, MERCHANT)["cursor"]
    intake(disputes, OTHER["merchant_id"])
    result = poll(updates, MERCHANT, cursor=cursor)
    assert result["cursor"] == cursor
    assert result["changed_case_ids"] == []
    assert result["reset"] is False


def test_case_filter_and_op_cross_case_queue_receive_only_their_actual_changes(stack):
    disputes, agent, updates, _ = stack
    first, second = intake(disputes), intake(disputes)
    agent.observe(first, "INTAKE")
    agent.observe(second, "INTAKE")
    case_cursor = poll(updates, OP, case_id=first["id"])["cursor"]
    queue_cursor = poll(updates, OP)["cursor"]
    comment(disputes, second)
    assert poll(updates, OP, case_id=first["id"], cursor=case_cursor)["changes"] == []
    assert poll(updates, OP, cursor=queue_cursor)["changed_case_ids"] == [second["id"]]


def test_cursor_survives_reader_restart_and_all_offline_changes_are_found(stack):
    disputes, agent, updates, path = stack
    first = intake(disputes)
    agent.observe(first, "INTAKE")
    cursor = poll(updates, OP)["cursor"]
    restarted = DisputeUpdatesService(SQLiteDisputeUpdateReader(path))
    assert poll(restarted, OP, cursor=cursor)["cursor"] == cursor
    first = comment(disputes, first)
    second = intake(disputes)
    agent.observe(first, "COMMENT")
    agent.converse(second["id"], OP, "离线期间完成分析", second["revision"])
    result = poll(restarted, OP, cursor=cursor)
    assert set(result["changed_case_ids"]) == {first["id"], second["id"]}
    assert result["reset"] is False
    assert poll(restarted, OP, cursor=result["cursor"])["changes"] == []


def test_database_replacement_causes_a_fresh_baseline_even_when_row_counts_match(stack):
    disputes, _, updates, path = stack
    old = intake(disputes)
    cursor = poll(updates, OP)["cursor"]
    path.unlink()
    replaced = DisputeService(SQLiteDisputeStore(path), clock=lambda: NOW)
    SQLiteDisputeAgentStore(path)
    new = intake(replaced)
    result = poll(updates, OP, cursor=cursor)
    assert result["reset"] is True
    assert result["changed_case_ids"] == [new["id"]]
    assert old["id"] not in json.dumps(result)


def test_cursor_scope_cannot_authorize_foreign_cases_and_filter_changes_reset(stack):
    disputes, _, updates, _ = stack
    own, foreign = intake(disputes), intake(disputes, OTHER["merchant_id"])
    cursor = poll(updates, OP)["cursor"]
    result = poll(updates, MERCHANT, cursor=cursor)
    assert result["reset"] is True
    assert result["changed_case_ids"] == [own["id"]]
    with pytest.raises(DisputeError) as error:
        poll(updates, MERCHANT, cursor=cursor, case_id=foreign["id"])
    assert error.value.status == 404
    scoped = poll(updates, OP, cursor=cursor, case_id=own["id"])
    assert scoped["reset"] is True
    assert scoped["changed_case_ids"] == [own["id"]]


@pytest.mark.parametrize("cursor", ["", "!invalid!", "e30", "W10", "a" * 2049])
def test_malformed_cursor_returns_validation_error(stack, cursor):
    with pytest.raises(DisputeError) as error:
        poll(stack[2], OP, cursor=cursor)
    assert error.value.code == "INVALID_CURSOR"


def test_forged_ahead_cursor_resets_instead_of_hiding_future_updates(stack):
    disputes, _, updates, _ = stack
    case = intake(disputes)
    baseline = poll(updates, OP)
    cursor = baseline["cursor"]
    payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    payload["positions"]["case"] = 100000
    forged = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    result = poll(updates, OP, cursor=forged)
    assert result["reset"] is True
    assert result["changed_case_ids"] == [case["id"]]


@pytest.mark.parametrize("timeout", [-1, 21, float("inf"), float("nan"), True, "20"])
def test_invalid_timeout_cannot_create_an_unbounded_wait(stack, timeout):
    with pytest.raises(DisputeError) as error:
        poll(stack[2], OP, timeout=timeout)
    assert error.value.code == "INVALID_TIMEOUT"


def test_idle_timeout_returns_same_cursor_and_does_not_hold_database_locks(stack):
    disputes, _, updates, _ = stack
    case = intake(disputes)
    cursor = poll(updates, OP)["cursor"]
    start = monotonic()
    result = poll(updates, OP, cursor=cursor, timeout=0.06)
    assert 0.04 <= monotonic() - start < 0.5
    assert result["timed_out"] is True
    assert result["cursor"] == cursor
    assert comment(disputes, case)["revision"] == 2


def test_disconnected_client_cancels_poll_promptly(stack):
    disputes, _, updates, _ = stack
    case = intake(disputes)
    cursor = poll(updates, OP)["cursor"]
    calls = 0

    async def disconnected():
        nonlocal calls
        calls += 1
        return calls >= 3

    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await updates.poll(OP, cursor=cursor, timeout=20, disconnected=disconnected)

    start = monotonic()
    asyncio.run(scenario())
    assert calls == 3
    assert monotonic() - start < 0.5
    assert comment(disputes, case)["revision"] == 2


def test_exclusive_database_lock_fails_within_bounded_response_budget(stack):
    disputes, _, updates, path = stack
    intake(disputes)
    cursor = poll(updates, OP)["cursor"]
    with sqlite3.connect(path) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        start = monotonic()
        try:
            with pytest.raises(DisputeError) as error:
                poll(updates, OP, cursor=cursor, timeout=20)
            assert error.value.code == "UPDATES_UNAVAILABLE"
            assert error.value.status == 503
            assert monotonic() - start < 1
        finally:
            writer.rollback()


def test_executor_or_reader_stall_has_an_outer_response_deadline():
    release = Event()

    class StalledReader:
        def read(self, identity, case_id, position):
            release.wait(timeout=1)
            return {}

    service = DisputeUpdatesService(StalledReader(), read_timeout=0.03)

    async def scenario():
        start = monotonic()
        try:
            with pytest.raises(DisputeError) as error:
                await service.poll(OP, timeout=20)
            assert error.value.code == "UPDATES_UNAVAILABLE"
            assert monotonic() - start < 0.2
        finally:
            release.set()

    asyncio.run(scenario())
