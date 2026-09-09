"""Explicit trusted test sessions for migrated V2 HTTP regression fixtures.

No production dependency is overridden. Auth-specific tests exercise the login
HTTP API separately; these regressions obtain real revocable server tokens.
"""

from uuid import uuid4

from oceanpilot.application.disputes import DisputeService

PASSWORD = "local-regression-only-password"
ROLES = ("OPERATOR", "MERCHANT", "RISK_OFFICER", "SUPERVISOR", "ADMIN", "DIRECTOR")


def session_headers(client, role="OPERATOR", merchant="synthetic-merchant-001"):
    if role not in ROLES:
        return {"Cookie": "oceanpilot_session=invalid-unprovisioned-role"}
    auth = client.app.state.v21_auth
    directory = {user["username"]: user for user in auth.list_users()}
    # Provision all decision makers before intake snapshots save participants.
    members = ("DIRECTOR",) if role == "DIRECTOR" else tuple(r for r in ROLES if r != "DIRECTOR")
    for member_role in members:
        name = f"{merchant[:45]}-{member_role.lower()}"
        if name not in directory:
            auth.create_user(
                username=name,
                password=PASSWORD,
                display_name=name,
                role=member_role,
                merchant_ids=[merchant],
                merchant_id=merchant if member_role == "MERCHANT" else None,
            )
    tokens = getattr(client.app.state, "test_session_tokens", {})
    key = (role, merchant)
    if key not in tokens:
        tokens[key] = auth.login(f"{merchant[:45]}-{role.lower()}", PASSWORD)[0]
    client.app.state.test_session_tokens = tokens
    token = tokens[key]
    return {"Cookie": f"oceanpilot_session={token}", "X-CSRF-Token": auth.csrf_token(token)}


def legacy_fixture_service(client):
    """Seed pre-V2.1 synthetic snapshots; HTTP always uses the real access policy."""
    actual = client.app.state.disputes
    return DisputeService(
        actual.store,
        clock=actual.clock,
        on_change=actual.on_change,
        case_library=actual.case_library,
    )


def seed_demo(client, scenario="A"):
    from oceanpilot.application.dispute_demo import create_demo, demo_identity

    session_headers(client)
    return create_demo(
        legacy_fixture_service(client),
        scenario,
        demo_identity("OPERATOR"),
        str(uuid4()),
    )["case"]


def normalized_intake(client, payload, merchant=None, *, role="OPERATOR", request_headers=None):
    """Create explicit synthetic registry facts, then call the real normalized HTTP entry.

    This is test setup, not an application compatibility path. Invalid event fields
    are still sent to HTTP DTO validation; the helper never fills monetary facts.
    Missing fixture source times are fixed once per source event for stable replay.
    """
    from datetime import UTC, datetime

    from pydantic import ValidationError

    from oceanpilot.api.dispute_intake import TransactionData

    data = payload.get("data", payload)
    merchant = (
        merchant
        or (data.get("merchant_id") if isinstance(data, dict) else None)
        or "synthetic-merchant-001"
    )
    if not isinstance(data, dict):
        return client.post(
            "/api/v2/intake/events",
            headers=request_headers
            if request_headers is not None
            else session_headers(client, role, merchant),
            json={"event": data, "confirmed": payload.get("confirmed", True)},
        )
    registry_fields = {
        "transaction_id",
        "merchant_id",
        "scheme",
        "channel",
        "amount_minor",
        "currency",
    }
    registry = {key: data[key] for key in registry_fields if key in data} | {
        "reference": "explicit-http-fixture-synthetic-transaction"
    }
    try:
        TransactionData.model_validate(registry)
    except ValidationError:
        pass
    else:
        registered = client.post(
            "/api/v2/director/transactions",
            headers=session_headers(client, "DIRECTOR", merchant),
            json=registry,
        )
        assert registered.status_code in {200, 409}, registered.text
    event = {
        key: value for key, value in data.items() if key not in {"event_id"} and value is not None
    }
    event["event_type"] = "FORMAL_DISPUTE"
    if "event_id" in data:
        event["source_event_id"] = data["event_id"]
    times = getattr(client.app.state, "test_source_event_times", {})
    key = str(data.get("event_id", payload.get("command_id")))
    times.setdefault(key, datetime.now(UTC).isoformat())
    client.app.state.test_source_event_times = times
    event.setdefault("received_at", times[key])
    event.setdefault("occurred_at", event["received_at"])
    return client.post(
        "/api/v2/intake/events",
        headers=request_headers
        if request_headers is not None
        else session_headers(client, role, merchant),
        json={"event": event, "confirmed": payload.get("confirmed", True)},
    )
