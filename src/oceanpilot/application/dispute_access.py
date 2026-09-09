"""Server-owned account scopes and explicit participants for the shared case."""

from copy import deepcopy

from oceanpilot.domain.dispute import require

SYSTEM_ACTORS = frozenset({"oceanpilot-workflow-agent", "oceanpilot-sla-scheduler"})


class DisputeAccessPolicy:
    def __init__(self, directory):
        self.directory = directory

    def _user(self, identity: dict) -> dict | None:
        user = self.directory.get_user(identity["actor_id"])
        if user and not user["disabled"] and user["role"] == identity["role"]:
            return user
        return None

    @staticmethod
    def _system(identity: dict) -> bool:
        return identity["role"] == "AGENT" and identity["actor_id"] in SYSTEM_ACTORS

    def can_access(self, case: dict, identity: dict) -> bool:
        if self._system(identity):
            return True
        user = self._user(identity)
        if user is None or user["role"] == "DIRECTOR":
            return False
        if case["merchant_id"] not in user["merchant_ids"]:
            return False
        participants = case.get("participants")
        # Legacy cases use explicit account-to-merchant grants until allocation.
        # A new case's saved participants narrow those grants to this case.
        return participants is None or any(
            item.get("user_id") == user["id"] for item in participants
        )

    def require_case(self, case: dict, identity: dict) -> None:
        require(self.can_access(case, identity), "NOT_FOUND", "案件不存在或你无权查看。", 404)

    def require_intake(self, merchant_id: str, identity: dict) -> None:
        user = self._user(identity)
        require(
            user is not None and user["role"] == "OPERATOR" and merchant_id in user["merchant_ids"],
            "FORBIDDEN",
            "你没有为此商户接收案件的授权。",
            403,
        )

    def case_participants(self, case: dict) -> list[dict]:
        existing = case.get("participants")
        identifiers = {item.get("user_id") for item in existing} if existing is not None else None
        return [
            {"user_id": user["id"], "role": user["role"], "display_name": user["display_name"]}
            for user in self.directory.list_users()
            if not user["disabled"]
            and user["role"] != "DIRECTOR"
            and case["merchant_id"] in user["merchant_ids"]
            and (identifiers is None or user["id"] in identifiers)
        ]

    def initialize_case(self, case: dict, identity: dict) -> dict:
        case = deepcopy(case)
        case["participants"] = self.case_participants(case)
        case["assigned_op_user_id"] = identity["actor_id"]
        user = self._user(identity)
        case["assigned_op"] = {
            "user_id": identity["actor_id"],
            "role": "OPERATOR",
            "display_name": user["display_name"] if user else "待分配运营人员",
        }
        return case
