"""Immediate tool observation plus coalesced, bounded model analysis of case events."""

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from oceanpilot.domain.dispute import DisputeError

_LOG = logging.getLogger(__name__)
_IDENTITY = {"role": "AGENT", "actor_id": "oceanpilot-event-agent"}
_AUDIENCE_MESSAGES = {
    "OPERATIONS": (
        "请向 OceanPayment 处理团队说明本案最新变化、商户响应和材料进度、审核阻断、"
        "上下游下一步及资金核对事项，并指出各项责任人。"
    ),
    "MERCHANT": (
        "请向本案商户解释最新进度、已有审核退回的具体原因、能否送审、缺少的材料，"
        "以及商户当前应做什么或等待谁处理。已作出的接受或抗辩选择不要重复要求确认。"
    ),
}
_CRITICAL = {
    "INTAKE",
    "CONFIRM_RULE",
    "MERCHANT_DECISION",
    "REGISTER_EVIDENCE",
    "WITHDRAW_EVIDENCE",
    "SUBMIT_EVIDENCE",
    "REVIEW",
    "SUBMIT",
    "RECORD_OUTCOME",
    "NEXT_STAGE",
    "RECONCILE",
    "CLOSE",
    "USER_RUN",
}


class DisputeAgentEvents:
    """Never hold a business transaction open while waiting for a remote model.

    Every accepted revision gets an immutable tool run. Live model work coalesces
    changes per case, and converse rejects a result if the case changes in flight.
    The queue is advisory: a restart can recover analysis through an explicit run.
    """

    def __init__(self, agent, *, enabled: bool = False):
        self.agent = agent
        self.enabled = enabled
        self._lock = Lock()
        self._pending: dict[str, tuple[int, str]] = {}
        self._running: set[str] = set()
        self._attempted: dict[str, int] = {}
        self._closed = False
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="v2-agent")

    def changed(self, case: dict, action: str, replayed: bool = False) -> None:
        self.agent.observe(case, action)
        if not replayed:
            self.schedule(case, action)

    def schedule(self, case: dict, trigger: str) -> None:
        if not self.enabled:
            return
        case_id, revision = case["id"], case["revision"]
        with self._lock:
            if self._closed or (trigger not in _CRITICAL and case_id not in self._running):
                return
            if self._attempted.get(case_id, 0) >= revision and trigger != "USER_RUN":
                return
            pending = self._pending.get(case_id)
            if pending and pending[0] >= revision:
                return
            self._pending[case_id] = (revision, trigger)
            if case_id not in self._running:
                self._running.add(case_id)
                self._pool.submit(self._drain, case_id)

    def is_pending(self, case_id: str) -> bool:
        with self._lock:
            return case_id in self._running

    def _drain(self, case_id: str) -> None:
        while True:
            with self._lock:
                job = self._pending.pop(case_id, None)
                if self._closed or job is None:
                    self._running.discard(case_id)
                    return
                revision, trigger = job
                self._attempted[case_id] = revision
            try:
                case = self.agent.disputes.get_case(case_id, _IDENTITY)
                if case["revision"] != revision:
                    self.schedule(case, trigger)
                    continue
                # Completed analyses survive process restart. Explicit user runs
                # may retry a failed model attempt, ordinary events do not repeat it.
                for audience, message in _AUDIENCE_MESSAGES.items():
                    prior = self.agent.store.list_conversations(case_id, audience=audience)
                    if trigger != "USER_RUN" and any(
                        item["case_revision"] == revision
                        and item.get("trigger", "").startswith("AUTO_EVENT:")
                        for item in prior
                    ):
                        continue
                    self.agent.converse(
                        case_id,
                        _IDENTITY,
                        message,
                        expected_revision=revision,
                        trigger=f"AUTO_EVENT:{trigger}",
                        audience=audience,
                    )
            except DisputeError as error:
                if error.code != "REVISION_CONFLICT":
                    _LOG.warning("V2 background agent analysis unavailable")
            except Exception:
                _LOG.warning("V2 background agent analysis unavailable")

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._pending.clear()
        self._pool.shutdown(wait=False, cancel_futures=True)
