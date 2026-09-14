"""Explicitly confirmed synthetic intake; resumable normal domain commands."""

import json
from contextlib import closing
from copy import deepcopy

from oceanpilot.domain.dispute import fingerprint, require, timestamp
from oceanpilot.domain.dispute_rules import match_rule


class DisputeSimulation:
    def __init__(self, intake):
        self.intake = intake
        self.disputes = intake.disputes
        with closing(intake.store._connect()) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS v21_simulations "
                "(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, snapshot TEXT NOT NULL)"
            )

    def preview(self, data, identity):
        identity = self.intake._operator(identity, data["merchant_id"])
        library = self.disputes.case_library
        require(library is not None, "LIBRARY_UNAVAILABLE", "案例库不可用。", 503)
        reference = library.get_reference(data["case_template_id"])
        require(reference is not None, "TEMPLATE_NOT_FOUND", "案例不存在。", 404)
        template = library.get_template(data["case_template_id"])
        matches = library.search(scheme=data["scheme"], reason_code=data["reason_code"], limit=100)
        scope_matches = any(x["template_id"] == data["case_template_id"] for x in matches)
        rule = match_rule(
            data["scheme"], "MOCK", data["reason_code"], "FORMAL_DISPUTE", data["received_at"]
        )
        automatic = bool(template and scope_matches and rule["allowed_actions"])
        if automatic:
            require(
                timestamp(rule["deadlines"]["merchant"]) > timestamp(self.intake._now()),
                "SIMULATION_DEADLINE_EXPIRED",
                "演练期限已过，请使用当前时间。",
                409,
            )
        else:
            rule = match_rule(
                data["scheme"],
                "CURATED_REFERENCE",
                data["reason_code"],
                "FORMAL_DISPUTE",
                data["received_at"],
            )
        self.disputes._screen_values(data)
        from oceanpilot.domain.chargeback import ChargebackEvidenceCode
        from oceanpilot.domain.evidence_catalog import describe

        return {
            "input": deepcopy(data),
            "reference": deepcopy(reference),
            "requires_rule_confirmation": not automatic,
            "scope_matches": scope_matches,
            "rule": rule,
            "materials": [
                {"code": code, "label": describe(ChargebackEvidenceCode(code)).label}
                for code in rule["required_evidence"]
            ],
            "confirmation_token": fingerprint(
                {"input": data, "rule": rule, "reference": reference}
            ),
            "production_eligible": False,
        }

    def create(self, data, identity, *, confirmed, confirmation_token, request_id):
        identity = self.intake._operator(identity, data["merchant_id"])
        require(
            confirmed is True, "CONFIRMATION_REQUIRED", "请明确确认本次合成事件和演练规则。", 422
        )
        key = "sim-" + fingerprint({"actor": identity["actor_id"], "request": request_id})
        request_hash = fingerprint({"data": data, "token": confirmation_token})
        with closing(self.intake.store._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT fingerprint,snapshot FROM v21_simulations WHERE id=?", (key,)
            ).fetchone()
            if row:
                require(
                    row["fingerprint"] == request_hash,
                    "IDEMPOTENCY_CONFLICT",
                    "同一次请求内容已变化，请恢复原请求或开始新的演练。",
                    409,
                )
                plan = json.loads(row["snapshot"])
            else:
                plan = self.preview(data, identity)
                require(
                    plan["confirmation_token"] == confirmation_token,
                    "PREVIEW_CHANGED",
                    "预览已变化，请重新核对。",
                    409,
                )
                db.execute(
                    "INSERT INTO v21_simulations VALUES (?,?,?)",
                    (key, request_hash, json.dumps(plan)),
                )
        # Stable server-derived identifiers keep partial retries on the same transaction/event.
        ref = "sim:" + "g".join(key[i : i + 8] for i in range(4, len(key), 8))
        event = {
            k: data[k]
            for k in (
                "merchant_id",
                "scheme",
                "reason_code",
                "amount_minor",
                "currency",
                "received_at",
                "case_template_id",
            )
        }
        event.update(
            channel="MOCK",
            transaction_id=ref,
            source_event_id=ref,
            event_type="FORMAL_DISPUTE",
            occurred_at=data["received_at"],
        )
        if plan.get("requires_rule_confirmation"):
            event["simulation_reference_id"] = event.pop("case_template_id")
        registry = {
            k: event[k]
            for k in (
                "channel",
                "transaction_id",
                "merchant_id",
                "scheme",
                "amount_minor",
                "currency",
            )
        }
        registry.update(
            reference="Confirmed template simulation: " + data["case_template_id"],
            source_type="OPERATOR_CONFIRMED_SYNTHETIC_SIMULATION",
            production_eligible=False,
            created_at=data["received_at"],
            created_by=identity["actor_id"],
        )
        self.intake.store.register(registry)
        result = self.intake.receive(event, identity, confirmed=True)
        if result["event"]["status"] != "PROCESSED":
            return result | {"simulation_status": "NEEDS_ATTENTION"}
        case = {"id": result["case_id"], "revision": result["command_receipt"]["revision"]}
        if plan.get("requires_rule_confirmation"):
            current = self.disputes.get_case(case["id"], identity)
            return result | {
                "case": current,
                "case_id": current["id"],
                "simulation_status": "NEEDS_RULE_CONFIRMATION",
                "notification_intent": None,
            }
        rule = plan["rule"]
        rule_data = {
            k: rule[k]
            for k in (
                "source_id",
                "source_locator",
                "rule_version",
                "required_evidence",
                "critical_evidence",
                "allowed_actions",
            )
        }
        rule_data.update(
            {
                name + "_deadline": rule["deadlines"][name]
                for name in ("merchant", "internal", "external")
            }
        )
        rule_data["reason"] = "操作员确认预览中的合成演练规则；不是银行或卡组织正式期限。"
        for action, payload, suffix in [
            ("CONFIRM_RULE", rule_data, "rule"),
            (
                "PUBLISH_TASK",
                {
                    "message": (
                        "收到一笔模拟拒付，请选择接受拒付或提出抗辩。提出抗辩后按清单上传材料。"
                    )
                },
                "task",
            ),
        ]:
            current = self.disputes.get_case(case["id"], identity)
            already_done = any(a["command_id"] == ref + ":" + suffix for a in current["audit"])
            require(
                already_done
                or timestamp(rule["deadlines"]["merchant"]) > timestamp(self.intake._now()),
                "SIMULATION_DEADLINE_EXPIRED",
                "演练期限已过，请运营人工核对当前案件。",
                409,
            )
            receipt = self.disputes.execute(
                {
                    "command_id": ref + ":" + suffix,
                    "action": action,
                    "case_id": case["id"],
                    "expected_revision": case["revision"],
                    "confirmed": True,
                    "data": payload,
                },
                identity,
            )
            case = receipt["case"]
        current = self.disputes.get_case(case["id"], identity)
        return result | {
            "case": current,
            "case_id": current["id"],
            "simulation_status": "READY",
            "notification_intent": {
                "kind": "MERCHANT_TASK_AVAILABLE",
                "id": ref + ":task",
                "active": current["work_status"] == "MERCHANT_ACTION_REQUIRED"
                and current["merchant_decision"] == "NONE",
                "case_id": current["id"],
                "revision": case["revision"],
                "merchant_id": current["merchant_id"],
                "delivery_status": "NOT_VERIFIED",
            },
        }
