"""Prepare a fresh synthetic case through authenticated HTTP; never edits storage.

Stops at a published merchant task. Decisions, evidence, reviews and outcomes remain
for the actual user flow. Each invocation creates a new case and sample directory.
"""

import argparse
import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from member_b_demo import code_identity, manifest, write_json


def prepare(directory, *, stage_demo=False, public_base_url=None):
    instance = manifest(directory)
    if instance.get("snapshot"):
        raise ValueError("Cannot prepare a backup snapshot")
    base_url = f"http://127.0.0.1:{instance['port']}"
    public_base_url = (public_base_url or base_url).rstrip("/")
    if public_base_url != base_url:
        from urllib.parse import urlsplit

        url = urlsplit(public_base_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path
            or url.hostname.endswith("trycloudflare.com")
        ):
            raise ValueError("Stage public URL must be a fixed HTTPS origin without credentials")
    if stage_demo and instance["code"]["sha256"] != code_identity()["sha256"]:
        raise ValueError("Build changed; verify and explicitly pin before preparing a stage case")
    records = json.loads((directory / "private-accounts.json").read_text())["accounts"]
    clients = {}
    trace = []
    run_id = str(uuid4())
    destination = directory / "rehearsals" / run_id
    destination.mkdir(parents=True, mode=0o700)

    def call(role, method, path, data=None):
        response = clients[role].request(method, path, json=data)
        trace.append({"role": role, "method": method, "path": path, "status": response.status_code})
        response.raise_for_status()
        return response

    try:
        for name in ("administrator", "operator-a", "merchant-a"):
            record = next(r for r in records if r["user"]["username"] == name)
            client = httpx.Client(base_url=base_url, timeout=30, trust_env=False)
            response = client.post(
                "/api/v2/session/login", json={"username": name, "password": record["password"]}
            )
            response.raise_for_status()
            client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
            clients[name] = client
        transaction = {
            "transaction_id": "B-VISA131-" + run_id[:12],
            "merchant_id": "merchant-a",
            "scheme": "VISA",
            "channel": "MOCK",
            "amount_minor": 12500,
            "currency": "USD",
            "reference": "MEMBER-B-SYNTHETIC-ONLY:" + run_id,
        }
        call("administrator", "POST", "/api/v2/admin/transactions", transaction)
        now = datetime.now(UTC).isoformat()
        event = {k: v for k, v in transaction.items() if k != "reference"} | {
            "event_type": "FORMAL_DISPUTE",
            "reason_code": "13.1",
            "source_event_id": "B-SYNTHETIC-" + run_id,
            "occurred_at": now,
            "received_at": now,
        }
        case = call(
            "operator-a", "POST", "/api/v2/intake/events", {"confirmed": True, "event": event}
        ).json()["case"]
        case = call(
            "operator-a",
            "POST",
            "/api/v2/commands",
            {
                "command_id": str(uuid4()),
                "case_id": case["id"],
                "expected_revision": case["revision"],
                "action": "PUBLISH_TASK",
                "confirmed": True,
                "data": {"message": "合成演练：请人工选择争议处理路径并上传本案材料。"},
            },
        ).json()["case"]
        if stage_demo:
            case = call(
                "merchant-a",
                "POST",
                "/api/v2/commands",
                {
                    "command_id": str(uuid4()),
                    "case_id": case["id"],
                    "expected_revision": case["revision"],
                    "action": "MERCHANT_DECISION",
                    "confirmed": True,
                    "data": {"decision": "CONTEST", "reason": "明确的合成发布会场景初始化。"},
                },
            ).json()["case"]
        samples = []
        for code in case["rule_snapshot"]["required_evidence"]:
            for variant in ("sufficient", "missing_field", "wrong_transaction"):
                path = f"/api/v2/cases/{case['id']}/collaboration/samples/{code}?variant={variant}"
                response = call("merchant-a", "GET", path)
                target = destination / f"{code}-{variant}.json"
                target.write_bytes(response.content)
                target.chmod(0o600)
                samples.append(
                    {
                        "file": target.name,
                        "code": code,
                        "variant": variant,
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                    }
                )
                if (
                    stage_demo
                    and variant == "sufficient"
                    and code != "fulfillment.proof_of_delivery"
                ):
                    from oceanpilot.domain.evidence_catalog import expected_source_of

                    uploader = (
                        "operator-a"
                        if expected_source_of(code) == "SYSTEM_OF_RECORD"
                        else "merchant-a"
                    )
                    case = call(
                        uploader,
                        "POST",
                        f"/api/v2/cases/{case['id']}/collaboration/files",
                        {
                            "command_id": str(uuid4()),
                            "expected_revision": case["revision"],
                            "code": code,
                            "title": "合成演示预置材料",
                            "filename": target.name,
                            "mime_type": "application/json",
                            "content_base64": base64.b64encode(response.content).decode(),
                        },
                    ).json()["case"]
        if stage_demo:
            from stage_materials import delivery_pdf

            files = []
            delivered_at = (
                (datetime.now(UTC) - timedelta(days=2)).replace(microsecond=0).isoformat()
            )
            for filename, delivered in [
                ("proof-of-delivery-v1-missing-time.pdf", None),
                ("proof-of-delivery-v2-complete.pdf", delivered_at),
            ]:
                target = destination / filename
                content = delivery_pdf(transaction, delivered_at=delivered)
                with target.open("xb") as stream:
                    stream.write(content)
                target.chmod(0o600)
                files.append({"path": str(target), "sha256": hashlib.sha256(content).hexdigest()})
            plan = call("merchant-a", "GET", f"/api/v2/cases/{case['id']}/plan").json()
            missing = [i["code"] for i in plan["checklist"] if not i["present"]]
            if len(plan["checklist"]) != 5 or missing != ["fulfillment.proof_of_delivery"]:
                raise ValueError("Stage initial evidence contract changed; do not use this case")
            if (case["work_status"], case["business_outcome"], case["finality"]) != (
                "EVIDENCE_COLLECTING",
                "UNKNOWN",
                "NOT_FINAL",
            ):
                raise ValueError("Stage initial state is not safe")
            write_json(
                destination / "stage-manifest.json",
                {
                    "synthetic_only": True,
                    "upstream": "mock",
                    "mode": "stage-demo",
                    "instance_id": instance["id"],
                    "run_id": run_id,
                    "case_id": case["id"],
                    "initial_revision": case["revision"],
                    "created_at": datetime.now(UTC).isoformat(),
                    "code_commit": instance["code"]["head"],
                    "build_sha256": instance["code"]["sha256"],
                    "merchant_url": public_base_url + f"/v2/merchant/cases/{case['id']}?stage=1",
                    "operations_url": public_base_url
                    + f"/v2/operations/cases/{case['id']}?stage=1",
                    "materials": files,
                    "missing": missing,
                    "expected_initial": {
                        "work_status": "EVIDENCE_COLLECTING",
                        "ready": "4/5",
                        "merchant_decision": "CONTEST",
                    },
                    "expected_final": {
                        "work_status": "OP_REVIEW",
                        "business_outcome": "UNKNOWN",
                        "finality": "NOT_FINAL",
                    },
                    "tenant_acceptance": "NOT_RUN",
                    "frozen_release": False,
                    "boundary": "新建合成案件；未认证真实飞书租户、网络或现场时长。"
                    "不得把工作树指纹当作已合入发布版本。",
                },
            )
        write_json(
            destination / "rehearsal.json",
            {
                "synthetic_only": True,
                "instance_id": instance["id"],
                "run_id": run_id,
                "case_id": case["id"],
                "transaction": transaction,
                "source_event": event,
                "reference_mapping": (
                    "Synthetic addition B-SYN-VISA131; not a real core case replay"
                ),
                "rule_snapshot": case["rule_snapshot"],
                "deadlines": case["deadlines"],
                "samples": samples,
                "trace": trace,
                "state": {
                    k: case[k] for k in ("revision", "work_status", "business_outcome", "finality")
                },
            },
        )
        print(
            json.dumps(
                {
                    "case_id": case["id"],
                    "materials": str(destination),
                    "merchant_url": public_base_url
                    + f"/v2/merchant/cases/{case['id']}"
                    + ("?stage=1" if stage_demo else ""),
                    **(
                        {"stage_manifest": str(destination / "stage-manifest.json")}
                        if stage_demo
                        else {}
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        for client in clients.values():
            client.close()
        write_json(destination / "http-trace.json", trace)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True, type=Path)
    parser.add_argument(
        "--stage-demo", action="store_true", help="Fresh audited 4/5 hero case; never resets data"
    )
    parser.add_argument("--public-base-url", help="Fixed HTTPS origin for the manifest links")
    args = parser.parse_args()
    prepare(
        args.instance.resolve(), stage_demo=args.stage_demo, public_base_url=args.public_base_url
    )
