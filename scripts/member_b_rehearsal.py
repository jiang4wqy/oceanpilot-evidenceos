"""Prepare a fresh synthetic case through authenticated HTTP; never edits storage.

Stops at a published merchant task. Decisions, evidence, reviews and outcomes remain
for the actual user flow. Each invocation creates a new case and sample directory.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from member_b_demo import manifest, write_json


def prepare(directory):
    instance = manifest(directory)
    if instance.get("snapshot"):
        raise ValueError("Cannot prepare a backup snapshot")
    base_url = f"http://127.0.0.1:{instance['port']}"
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
        for name in ("director", "operator-a", "merchant-a"):
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
        call("director", "POST", "/api/v2/director/transactions", transaction)
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
                    "merchant_url": base_url + "/v2/merchant",
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
    prepare(parser.parse_args().instance.resolve())
