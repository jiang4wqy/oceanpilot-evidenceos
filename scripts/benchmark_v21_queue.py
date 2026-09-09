"""Reproducible synthetic queue benchmark; never reads or mutates user databases."""

import argparse
import json
import sqlite3
import statistics
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from oceanpilot.adapters.persistence.dispute_identity import SQLiteDisputeIdentity
from oceanpilot.adapters.persistence.dispute_queue import DisputeQueueReader
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.dispute_access import DisputeAccessPolicy


def sample(call, iterations):
    call()  # Warmup both readers before collecting the same number of observations.
    values = []
    payload = 0
    for _ in range(iterations):
        started = time.perf_counter()
        response = call()
        encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode()
        values.append((time.perf_counter() - started) * 1000)
        payload = len(encoded)
    return {
        "payload_bytes": payload,
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(sorted(values)[int(0.95 * (len(values) - 1))], 3),
        "iterations": iterations,
    }


def benchmark(count, iterations):
    with tempfile.TemporaryDirectory(prefix="oceanpilot-v21-benchmark-") as directory:
        db_path = Path(directory) / "queue.db"
        store = SQLiteDisputeStore(db_path)
        auth = SQLiteDisputeIdentity(db_path)
        user = auth.create_user(
            username="benchmark-merchant",
            password="benchmark-only-password",
            display_name="合成基准商户",
            role="MERCHANT",
            merchant_id="bench-a",
            merchant_ids=["bench-a"],
        )
        identity = {"actor_id": user["id"], "role": "MERCHANT", "merchant_id": "bench-a"}
        policy = DisputeAccessPolicy(auth)
        reader = DisputeQueueReader(store, policy)
        now = datetime(2026, 9, 9, tzinfo=UTC)
        rows = []
        for index in range(count):
            merchant = "bench-a" if index % 2 == 0 else "bench-b"
            case = {
                "id": f"BENCH-CASE-{index}",
                "revision": 25,
                "merchant_id": merchant,
                "transaction_id": f"BENCH-TX-{index}",
                "scheme": "VISA",
                "reason_code": "13.1",
                "amount_minor": 10000,
                "currency": "USD",
                "stage": "FORMAL_DISPUTE",
                "stage_number": 1,
                "work_status": "EVIDENCE_COLLECTING",
                "merchant_decision": "CONTEST",
                "finality": "NOT_FINAL",
                "financial_status": "PENDING",
                "production_eligible": False,
                "deadlines": {"merchant": "2026-09-12T00:00:00Z"},
                "tasks": [],
                "audit": [{"fixture": True, "text": "合成基准日志 " * 80} for _ in range(25)],
                "evidence": [{"fixture": True, "notes": "合成证据内容 " * 80} for _ in range(5)],
            }
            rows.append((case["id"], merchant, 25, json.dumps(case, ensure_ascii=False)))
        with sqlite3.connect(db_path) as connection:
            connection.executemany("INSERT INTO v2_dispute_cases VALUES (?,?,?,?)", rows)
        before = sample(lambda: {"cases": store.list_cases("bench-a")}, iterations)
        after = sample(lambda: reader.read(identity, limit=25, now=now), iterations)
        # Measure a SQLite read actually held behind an exclusive writer. This is
        # a controlled contention probe, not inferred production lock telemetry.
        acquired = threading.Event()

        def hold_exclusive():
            with sqlite3.connect(db_path) as writer:
                writer.execute("BEGIN EXCLUSIVE")
                acquired.set()
                time.sleep(0.05)
                writer.rollback()

        holder = threading.Thread(target=hold_exclusive)
        holder.start()
        acquired.wait()
        with sqlite3.connect(db_path, timeout=2) as blocked:
            started = time.perf_counter()
            blocked.execute("SELECT count(*) FROM v2_dispute_cases").fetchone()
            lock_probe_ms = (time.perf_counter() - started) * 1000
        holder.join()
        return {
            "total_cases": count,
            "authorized_cases": count // 2,
            "page_size": 25,
            "fixture_audit_rows_per_case": 25,
            "fixture_evidence_per_case": 5,
            "before_full_aggregate": before,
            "after_scoped_summary": after,
            "sqlite_exclusive_hold_ms": 50,
            "sqlite_blocked_read_ms": round(lock_probe_ms, 3),
            "database_bytes": db_path.stat().st_size,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="work/v21-queue-benchmark.json")
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    if args.iterations < 20:
        parser.error("At least 20 iterations are needed for the reported P95.")
    report = {
        "synthetic_only": True,
        "created_at": datetime.now(UTC).isoformat(),
        "measurement": (
            "Local SQL read + JSON encoding; excludes HTTP transport and browser render."
        ),
        "baseline": "Pre-V2.1 list response: all authorized full aggregates.",
        "limitations": (
            "Warm local filesystem; controlled 50 ms exclusive SQLite lock probe; "
            "not production SLO."
        ),
        "results": [benchmark(count, args.iterations) for count in (100, 1000)],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
