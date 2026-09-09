"""One response boundary for permissions, action forms, and role-specific views."""

from copy import deepcopy

from oceanpilot.application.dispute_views import case_summary, case_view, merchant_plan_view
from oceanpilot.domain.dispute import ACTION_ROLES
from oceanpilot.domain.dispute_rules import case_plan


def command_models():
    from oceanpilot.api.disputes import DATA_MODELS

    return DATA_MODELS


def command_schema(model) -> dict:
    schema = model.model_json_schema()
    required = schema.get("required", [])
    definitions = schema.get("$defs", {})
    fields = {}
    for name, original in schema.get("properties", {}).items():
        item = deepcopy(original)
        if "$ref" in item:
            item = definitions[item["$ref"].rsplit("/", 1)[1]] | item
        if "anyOf" in item:
            choices = [choice for choice in item["anyOf"] if choice.get("type") != "null"]
            if len(choices) == 1:
                item = choices[0] | {key: value for key, value in item.items() if key != "anyOf"}
        fields[name] = item | {"name": name, "required": name in required}
        if "maxLength" in item:
            fields[name]["max_length"] = item["maxLength"]
        if "minLength" in item:
            fields[name]["min_length"] = item["minLength"]
    return {"fields": fields, "required_fields": required}


def owner_for(case: dict, role: str | None, identity: dict, policy=None) -> dict:
    participants = policy.case_participants(case) if policy else case.get("participants", [])
    preferred = case.get("assigned_op_user_id") if role == "OPERATOR" else identity.get("actor_id")
    person = next(
        (
            person
            for person in participants
            if person["role"] == role and person["user_id"] == preferred
        ),
        None,
    )
    if person is None:
        person = next((person for person in participants if person["role"] == role), None)
    labels = {
        "MERCHANT": "商户协作人",
        "OPERATOR": "运营人员",
        "RISK_OFFICER": "风控审核员",
        "SUPERVISOR": "主管",
        "ADMIN": "知识管理员",
    }
    return (
        deepcopy(person)
        if person
        else {"user_id": None, "role": role, "display_name": labels.get(role, "待分配")}
    )


def available_actions(case: dict, identity: dict, service) -> list[dict]:
    result = []
    for action, roles in ACTION_ROLES.items():
        if identity["role"] not in roles or action not in command_models() or action == "INTAKE":
            continue
        # Shared chat and time-driven monitoring have their own cursors and APIs.
        if action in {"COMMENT", "MONITOR_SLA"}:
            continue
        gate = service.action_gate(case, action, identity)
        fields = command_schema(command_models()[action])
        choices = {name: item["enum"] for name, item in fields["fields"].items() if "enum" in item}
        selected = gate.get("choices")
        if isinstance(selected, list):
            choices["decision"] = selected
        elif isinstance(selected, dict):
            choices.update(selected)
        result.append(
            {
                "action": action,
                "visible": True,
                "enabled": gate["enabled"],
                "blocked_reason": gate.get("blocked_reason"),
                "code": gate.get("code"),
                "owner": owner_for(case, gate.get("owner"), identity, service.access_policy),
                "revision": case["revision"],
                "expected_revision": case["revision"],
                "choices": choices,
                **fields,
            }
        )
    return result


def present_case(case: dict, identity: dict, service) -> dict:
    result = case_view(case, identity, service.access_policy)
    collaboration = getattr(service, "collaboration", None)
    if collaboration is not None and collaboration.open_handoffs(case["id"]):
        result["close_gate"]["enabled"] = False
        result["close_gate"]["handoffs_resolved"] = False
        result["close_gate"]["blockers"].append("尚有未解决的人工接手事项。")
    else:
        result["close_gate"]["handoffs_resolved"] = True
    actions = available_actions(case, identity, service)
    result["available_actions"] = actions
    plan = case_plan(case, now=service.clock())
    next_action = plan.get("next_action", {})
    wanted = next_action.get("action")
    primary = next((item for item in actions if item["action"] == wanted and item["enabled"]), None)
    if primary is None:
        preferred = (
            "RESOLVE_RESPONSE",
            "VERIFY_OUTCOME",
            "PROCESS_ACCEPT",
            "FINAL_REVIEW",
            "REVIEW",
            "SUBMIT_EVIDENCE",
            "REGISTER_EVIDENCE",
            "PUBLISH_TASK",
            "CONFIRM_RULE",
            "MERCHANT_DECISION",
            "BUILD_PACKAGE",
            "SUBMIT",
            "RECONCILE",
            "NOTIFY_MERCHANT",
            "CLOSE",
        )
        primary = next(
            (
                item
                for name in preferred
                for item in actions
                if item["action"] == name and item["enabled"]
            ),
            None,
        )
    result["primary_action"] = primary
    result["current_task"] = {
        "action": wanted,
        "reason": next_action.get("reason"),
        "owner": owner_for(case, next_action.get("owner"), identity, service.access_policy),
    }
    if identity["role"] == "MERCHANT" and case.get("work_status") == "CLOSED":
        result["primary_action"] = None
        result["current_task"] = {
            "action": "CLOSED",
            "reason": "案件处理已结束，可查看当前结果与资金说明。",
            "owner": {"user_id": None, "role": None, "display_name": "已结束"},
        }
    return result


def present_result(result: dict, identity: dict, service) -> dict:
    output = deepcopy(result)
    if isinstance(result.get("case"), dict):
        output["case"] = present_case(result["case"], identity, service)
    if identity["role"] == "MERCHANT" and "receipt" in output:
        output["receipt"] = {
            key: value
            for key, value in output["receipt"].items()
            if key in {"command_id", "case_id", "revision", "action", "status", "executed_at"}
        }
    return output


def present_plan(plan: dict, identity: dict, case: dict, service) -> dict:
    result = merchant_plan_view(plan) if identity["role"] == "MERCHANT" else deepcopy(plan)
    if identity["role"] == "MERCHANT" and case.get("work_status") == "CLOSED":
        result["next_action"] = {
            "action": "CLOSED",
            "owner": None,
            "reason": "案件处理已结束，可查看当前结果与资金说明。",
        }
    result["available_actions"] = available_actions(case, identity, service)
    return result


def present_summary(case: dict, identity: dict) -> dict:
    return case_summary(case, identity)
