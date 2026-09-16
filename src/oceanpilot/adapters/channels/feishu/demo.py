"""Feishu rehearsal composition using B's normalized intake and real commands.

Reset retires only case IDs recorded by this component. It never deletes a case,
audit, account, evidence file, or other pre-existing business data.
"""

from datetime import UTC, datetime
from uuid import UUID

from oceanpilot.adapters.channels.feishu.v2 import FeishuV2Error
from oceanpilot.domain.dispute import require


class FeishuDemoBatches:
    def __init__(self, bot, intake):
        self.bot, self.intake = bot, intake

    def begin(self, batch_id, *, administrator, operators, merchants, confirmed):
        # Require an explicit reset intent. Persist inputs before invoking B so
        # restarting this exact batch replays the same intake and command IDs.
        require(confirmed is True, "CONFIRMATION_REQUIRED", "Confirm synthetic reset")
        require(str(UUID(batch_id)) == batch_id, "INVALID_BATCH", "Use a canonical UUID")
        admin = self.bot.identity(administrator)
        require(admin["role"] == "ADMIN", "FORBIDDEN", "Synthetic registry needs IT admin", 403)
        require(
            len(merchants) == len(operators) == 2 and merchants[0] != merchants[1],
            "INVALID_DEMO_SCOPE",
            "Two isolated synthetic merchants required",
        )
        for merchant, actor in zip(merchants, operators, strict=True):
            identity = self.bot.identity(actor)
            require(identity["role"] == "OPERATOR", "FORBIDDEN", "Use a real scoped Operator")
            self.bot.disputes.access_policy.require_intake(merchant, identity)
        spec = {"administrator": administrator, "operators": operators, "merchants": merchants}
        with self.bot.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row, batch = self.bot.record(db, "demo", batch_id)
            if row:
                require(batch["spec"] == spec, "DEMO_BATCH_CONFLICT", "Batch inputs differ")
                require(row["state"] != "RETIRED", "DEMO_BATCH_RETIRED", "Start a new batch")
            else:
                previous = db.execute(
                    "SELECT * FROM fp_records WHERE kind='demo' AND state!='RETIRED'"
                ).fetchall()
                for old in previous:
                    value = self.bot.unseal("demo" + old["ref"], old["body"])
                    for case_id in value["cases"]:
                        self.bot.put(
                            db,
                            "retired",
                            case_id,
                            "",
                            "RETIRED",
                            {"batch": old["ref"], "replacement": batch_id},
                        )
                    self.bot.put(db, "demo", old["ref"], old["owner"], "RETIRED", value)
                # Invalidate even selection-card jobs that contain several case IDs.
                for record in db.execute(
                    "SELECT * FROM fp_records WHERE kind IN ('card','job') "
                    "AND state NOT IN ('SENT','UNCERTAIN','SENDING','REVOKED','BLOCKED')"
                ).fetchall():
                    value = self.bot.unseal(record["kind"] + record["ref"], record["body"])
                    if value.get("case_id") and self.bot.record(db, "retired", value["case_id"])[0]:
                        self.bot.put(
                            db,
                            record["kind"],
                            record["ref"],
                            record["owner"],
                            "REVOKED" if record["kind"] == "card" else "BLOCKED",
                            value,
                        )
                batch = {
                    "spec": spec,
                    "created_at": datetime.now(UTC).isoformat(),
                    "cases": [],
                    "synthetic": True,
                    "upstream": "MOCK",
                }
                self.bot.put(db, "demo", batch_id, administrator, "PREPARING", batch)
        # A failure leaves a resumable PREPARING record. No automatic merchant
        # decision, evidence approval, package approval or upstream submission.
        for number, (merchant, actor) in enumerate(zip(merchants, operators, strict=True)):
            facts = {
                "transaction_id": f"feishu-{batch_id}-{number}",
                "merchant_id": merchant,
                "scheme": "VISA",
                "channel": "MOCK",
                "amount_minor": 12800,
                "currency": "USD",
            }
            self.intake.register_transaction(
                facts
                | {"reference": "Synthetic product-not-received rehearsal; not a bank record"},
                admin,
            )
            identity = self.bot.identity(actor)
            received = self.intake.receive(
                facts
                | {
                    "source_event_id": f"feishu-{batch_id}-{number}",
                    "event_type": "FORMAL_DISPUTE",
                    "reason_code": "13.1",
                    "received_at": batch["created_at"],
                    "occurred_at": batch["created_at"],
                },
                identity,
                confirmed=True,
            )
            require(
                received["case_id"] is not None,
                "DEMO_INTAKE_BLOCKED",
                "Inspect normalized inbox; do not invent a case",
            )
            case = self.bot.disputes.get_case(received["case_id"], identity)
            with self.bot.db() as db:
                db.execute("BEGIN IMMEDIATE")
                current, batch = self.bot.record(db, "demo", batch_id)
                if current["state"] == "RETIRED":
                    # A concurrent reset must not leave an untracked, active old case.
                    self.bot.put(db, "retired", case["id"], "", "RETIRED", {"batch": batch_id})
                if case["id"] not in batch["cases"]:
                    batch["cases"].append(case["id"])
                self.bot.put(db, "demo", batch_id, administrator, current["state"], batch)
            if current["state"] == "RETIRED":
                raise FeishuV2Error("DEMO_BATCH_RETIRED", 409)
            # The only demonstration preparation is the existing operator publish gate.
            # It validates the rule and deadline; an unverified source fails closed.
            command_id = f"feishu-publish-{batch_id}-{number}"
            if not self.bot.disputes.store.get_command_fingerprint(command_id):
                self.bot.disputes.execute(
                    {
                        "command_id": command_id,
                        "case_id": case["id"],
                        "expected_revision": case["revision"],
                        "action": "PUBLISH_TASK",
                        "confirmed": True,
                        "data": {},
                    },
                    identity,
                )
        with self.bot.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row, batch = self.bot.record(db, "demo", batch_id)
            require(row["state"] != "RETIRED", "DEMO_BATCH_RETIRED", "Start a new batch")
            self.bot.put(db, "demo", batch_id, administrator, "READY", batch)
        return {
            "batch_id": batch_id,
            "cases": batch["cases"],
            "synthetic": True,
            "upstream": "MOCK",
        }
