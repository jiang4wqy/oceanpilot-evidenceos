"""Durable observation and conversation storage for the V2 workflow agent."""

from typing import Protocol

AUDIENCES = {"MERCHANT", "OPERATIONS", "SHARED", "OP_INTERNAL"}


def audience_for_role(role: str | None) -> str:
    return "MERCHANT" if role == "MERCHANT" else "OPERATIONS"


def conversation_audience(conversation: dict) -> str:
    """Legacy automatic/unknown records stay internal; never infer a merchant reader."""
    audience = conversation.get("audience")
    if audience in AUDIENCES:
        return audience
    if audience is not None or str(conversation.get("trigger", "")).startswith("AUTO_EVENT:"):
        return "OPERATIONS"
    return audience_for_role(conversation.get("actor_role"))


class DisputeAgentStore(Protocol):
    def get_run(self, case_id: str, revision: int) -> dict | None: ...

    def list_runs(self, case_id: str, limit: int = 100) -> list[dict]: ...

    def get_proposal(self, case_id: str, proposal_id: str) -> dict | None: ...

    def save_run(self, run: dict) -> dict: ...

    def list_conversations(
        self, case_id: str, limit: int = 100, *, audience: str = "OPERATIONS"
    ) -> list[dict]: ...

    def save_conversation(self, conversation: dict) -> dict: ...


class DisputeCaseKnowledge(Protocol):
    """Read-only references; retrieval never supplies executable case rules."""

    def manifest(self) -> dict: ...

    def search(
        self, *, scheme: str, reason_code: str, query: str | None = None, limit: int = 5
    ) -> list[dict]: ...

    def get_reference(self, template_id: str) -> dict | None: ...

    def get_template(self, template_id: str) -> dict | None: ...
