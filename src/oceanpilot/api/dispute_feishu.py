"""Signed callbacks and locally authorized test-chat delivery; default disabled."""

import os
import sqlite3
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr
from starlette.concurrency import run_in_threadpool

from oceanpilot.adapters.channels.feishu.v2 import (
    FeishuV2Adapter,
    FeishuV2Error,
    FeishuV2Store,
    TrustedBindings,
)
from oceanpilot.adapters.feishu.security import FeishuRequestVerifier, FeishuVerificationError
from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.api.disputes import Identity

router = APIRouter(
    prefix="/api/v2/integrations/feishu",
    tags=["V2 Feishu"],
    responses={404: PROBLEM_RESPONSE, 409: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
MAX_BODY_BYTES = 64 * 1024


def initialize_dispute_feishu(
    app: FastAPI,
    db_path: Path,
    base_url: str = "http://127.0.0.1:8000",
    *,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Call inside lifespan, after app.state.disputes exists; fail closed."""
    env = os.environ if environ is None else environ
    app.state.dispute_feishu = None
    app.state.dispute_feishu_verifier = None
    app.state.dispute_feishu_outbox = None
    required = (
        "OCEANPILOT_V2_FEISHU_BINDINGS_JSON",
        "FEISHU_ENCRYPT_KEY",
        "FEISHU_VERIFICATION_TOKEN",
    )
    if not all(env.get(key) for key in required):
        return False
    try:
        bindings = TrustedBindings.from_json(env[required[0]])
        from oceanpilot.domain.dispute_rules import case_plan

        adapter = FeishuV2Adapter(
            app.state.disputes,
            bindings,
            FeishuV2Store(db_path),
            base_url=base_url,
            plan=case_plan,
        )
        verifier = FeishuRequestVerifier(
            encrypt_key=env["FEISHU_ENCRYPT_KEY"],
            verification_token=env["FEISHU_VERIFICATION_TOKEN"],
            now=lambda: int(time.time()),
        )
    except (ValueError, TypeError):
        return False
    app.state.dispute_feishu, app.state.dispute_feishu_verifier = adapter, verifier
    from oceanpilot.adapters.channels.feishu.outbox import FeishuDisputeOutbox, load_test_targets
    from oceanpilot.adapters.feishu.client import FeishuOutboundClient

    try:
        targets = load_test_targets(env.get("OCEANPILOT_V21_FEISHU_TEST_TARGETS_JSON"), bindings)
    except ValueError:
        targets = {}
    client = None
    if (
        targets
        and env.get("OCEANPILOT_V21_FEISHU_OUTBOUND") == "authorized-test"
        and env.get("FEISHU_APP_ID")
        and env.get("FEISHU_APP_SECRET")
    ):
        client = FeishuOutboundClient(
            app_id=env["FEISHU_APP_ID"], app_secret=env["FEISHU_APP_SECRET"]
        )
    outbox = FeishuDisputeOutbox(adapter, targets=targets, client=client)
    adapter.outbox = outbox
    app.state.dispute_feishu_outbox = outbox
    outbox.start()
    return True


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={"type": "about:blank", "title": code, "status": status, "code": code},
    )


async def _handle(request: Request, mode: str) -> JSONResponse:
    adapter = getattr(request.app.state, "dispute_feishu", None)
    verifier = getattr(request.app.state, "dispute_feishu_verifier", None)
    if adapter is None or verifier is None:
        return _error(503, "FEISHU_V2_DISABLED")
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        return _error(415, "UNSUPPORTED_MEDIA_TYPE")
    for name in (b"x-lark-request-timestamp", b"x-lark-request-nonce", b"x-lark-signature"):
        if sum(key.lower() == name for key, _ in request.headers.raw) > 1:
            return _error(401, "VERIFICATION_FAILED")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            return _error(413, "PAYLOAD_TOO_LARGE")
        chunks.append(chunk)
    try:
        payload = verifier.verify(
            dict(request.headers), b"".join(chunks), allow_url_verification=True
        )
    except FeishuVerificationError:
        return _error(401, "VERIFICATION_FAILED")
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not isinstance(challenge, str) or not challenge or len(challenge) > 2048:
            return _error(400, "INVALID_CALLBACK")
        return JSONResponse({"challenge": challenge})
    try:
        response = await run_in_threadpool(adapter.handle, payload, mode=mode)
        return JSONResponse(response)
    except FeishuV2Error as exc:
        return _error(exc.status, exc.code)
    except sqlite3.Error:
        return _error(503, "FEISHU_V2_STORAGE_UNAVAILABLE")
    except Exception as exc:
        from oceanpilot.domain.dispute import DisputeError

        if isinstance(exc, DisputeError):
            return _error(exc.status, exc.code)
        # Callback bodies, token values and exception details never enter responses.
        return _error(500, "FEISHU_V2_INTERNAL_ERROR")


@router.post("/events")
async def dispute_feishu_events(request: Request) -> JSONResponse:
    return await _handle(request, "events")


@router.post("/card")
async def dispute_feishu_card(request: Request) -> JSONResponse:
    return await _handle(request, "card")


class OutboxPreviewDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    command_id: StrictStr = Field(min_length=8, max_length=200)
    case_id: StrictStr = Field(min_length=1, max_length=128)
    target_ref: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    kind: Literal[
        "NEW_DISPUTE", "MISSING_EVIDENCE", "SLA_REMINDER", "REVIEW_FEEDBACK", "SUMMARY"
    ] = "NEW_DISPUTE"


class OutboxSendDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    confirmed: StrictBool


async def _outbox_call(request, method, *args, **kwargs):
    outbox = getattr(request.app.state, "dispute_feishu_outbox", None)
    if outbox is None:
        return _error(503, "FEISHU_V2_DISABLED")
    try:
        return await run_in_threadpool(getattr(outbox, method), *args, **kwargs)
    except FeishuV2Error as exc:
        return _error(exc.status, exc.code)
    except sqlite3.Error:
        return _error(503, "FEISHU_V2_STORAGE_UNAVAILABLE")


@router.get("/outbox")
async def list_outbox(request: Request, identity: Identity, case_id: str):
    return await _outbox_call(request, "list_for_case", case_id, identity)


@router.post("/outbox")
async def preview_outbox(payload: OutboxPreviewDTO, request: Request, identity: Identity):
    return await _outbox_call(request, "preview", identity=identity, **payload.model_dump())


@router.post("/outbox/{outbox_id}/send")
async def send_outbox(outbox_id: str, payload: OutboxSendDTO, request: Request, identity: Identity):
    return await _outbox_call(request, "send", outbox_id, identity, confirmed=payload.confirmed)
