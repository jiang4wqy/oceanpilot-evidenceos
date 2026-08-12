import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from oceanpilot.adapters.feishu.cards import NeedInfoCardInput, render_need_info_card
from oceanpilot.adapters.feishu.client import FeishuOutboundError, FeishuReceiveIdType
from oceanpilot.adapters.feishu.security import FeishuVerificationError
from oceanpilot.adapters.feishu.store import (
    ReceiptConflict,
    ReceiptOutcome,
)
from oceanpilot.api.cases import PROBLEM_RESPONSE
from oceanpilot.api.dependencies import FeishuRuntime, get_feishu_runtime
from oceanpilot.api.errors import (
    FeishuCallbackTooLarge,
    FeishuCallbackUnauthorized,
    FeishuIdempotencyConflict,
    FeishuInvalidCallback,
    FeishuUnavailable,
)
from oceanpilot.api.feishu_schemas import (
    FeishuCallbackAcknowledgement,
    FeishuUrlVerificationPayload,
    FeishuUrlVerificationResponse,
    parse_feishu_message_event,
)
from oceanpilot.application.feishu_models import FeishuFlowOutcome, FeishuIncident
from oceanpilot.application.feishu_orchestrator import FeishuBindingInProgress

router = APIRouter(prefix="/api/v1/feishu")
_MAX_CALLBACK_BYTES = 65_536
_EVENT_CLAIM_LEASE = timedelta(seconds=30)

_CALLBACK_PROBLEMS = {
    401: PROBLEM_RESPONSE,
    409: PROBLEM_RESPONSE,
    413: PROBLEM_RESPONSE,
    422: PROBLEM_RESPONSE,
    500: PROBLEM_RESPONSE,
    503: PROBLEM_RESPONSE,
}
_CALLBACK_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"type": "object"},
            }
        },
    }
}


async def _read_callback_body(request: Request) -> bytes:
    content_types = request.headers.getlist("content-type")
    if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != (
        "application/json"
    ):
        raise FeishuInvalidCallback()

    declared_lengths = request.headers.getlist("content-length")
    if len(declared_lengths) > 1:
        raise FeishuInvalidCallback()
    declared_length = None
    if declared_lengths:
        declared = declared_lengths[0]
        if (
            len(declared) > 20
            or not declared.isascii()
            or not declared.isdecimal()
        ):
            raise FeishuInvalidCallback()
        try:
            declared_length = int(declared)
        except ValueError:
            raise FeishuInvalidCallback() from None
        if declared_length > _MAX_CALLBACK_BYTES:
            raise FeishuCallbackTooLarge()

    chunks: list[bytes] = []
    actual_length = 0
    async for chunk in request.stream():
        actual_length += len(chunk)
        if actual_length > _MAX_CALLBACK_BYTES:
            raise FeishuCallbackTooLarge()
        chunks.append(chunk)
    if declared_length is not None and declared_length != actual_length:
        raise FeishuInvalidCallback()
    return b"".join(chunks)


async def _verified_payload(
    request: Request,
    runtime: FeishuRuntime,
) -> tuple[dict[str, object], bytes]:
    raw_body = await _read_callback_body(request)
    try:
        return runtime.verifier.verify(request.headers, raw_body), raw_body
    except FeishuVerificationError:
        raise FeishuCallbackUnauthorized() from None


@router.post(
    "/events",
    response_model=FeishuUrlVerificationResponse | FeishuCallbackAcknowledgement,
    responses=_CALLBACK_PROBLEMS,
    openapi_extra=_CALLBACK_OPENAPI,
)
async def receive_event(
    request: Request,
    runtime: Annotated[FeishuRuntime, Depends(get_feishu_runtime)],
) -> FeishuUrlVerificationResponse | FeishuCallbackAcknowledgement:
    payload, raw_body = await _verified_payload(request, runtime)
    try:
        verification = FeishuUrlVerificationPayload.model_validate(payload)
    except ValidationError:
        verification = None
    if verification is not None:
        return FeishuUrlVerificationResponse(challenge=verification.challenge)

    try:
        callback = parse_feishu_message_event(payload)
    except (TypeError, ValidationError):
        raise FeishuInvalidCallback() from None
    if not hmac.compare_digest(
        callback.header.app_id.encode(),
        runtime.app_id.encode(),
    ):
        raise FeishuCallbackUnauthorized()
    message = callback.event.message
    if callback.event.sender.sender_type == "app":
        return FeishuCallbackAcknowledgement()
    if runtime.demo_chat_id is None or runtime.demo_merchant_ref is None:
        raise FeishuUnavailable()
    if not hmac.compare_digest(
        message.chat_id.encode(),
        runtime.demo_chat_id.encode(),
    ):
        return FeishuCallbackAcknowledgement()

    context = request.state.request_context
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    claim_token = secrets.token_hex(32)
    received_at = datetime.now(UTC)
    try:
        occurred_at = datetime.fromtimestamp(
            int(callback.header.create_time) / 1000,
            UTC,
        )
    except (OSError, OverflowError, ValueError):
        raise FeishuInvalidCallback() from None
    try:
        with runtime.store_factory.session() as store:
            receipt = store.claim_event(
                callback.header.event_id,
                payload_hash=payload_hash,
                claim_token=claim_token,
                now=received_at.isoformat(),
                lease_expires_at=(received_at + _EVENT_CLAIM_LEASE).isoformat(),
            )
    except ReceiptConflict:
        raise FeishuIdempotencyConflict() from None
    except (OSError, sqlite3.Error, ValueError):
        raise FeishuUnavailable() from None
    if receipt.outcome is ReceiptOutcome.IN_PROGRESS:
        raise FeishuUnavailable()
    if receipt.outcome is ReceiptOutcome.REPLAY:
        return FeishuCallbackAcknowledgement()

    thread_id = message.root_id or message.message_id
    binding_material = json.dumps(
        [callback.header.tenant_key, message.chat_id, thread_id],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode()
    binding_key = f"feishu:{hashlib.sha256(binding_material).hexdigest()}"
    try:
        result = runtime.orchestrator.start_incident(
            FeishuIncident(
                binding_key=binding_key,
                event_id=callback.header.event_id,
                summary=message.content.text,
                merchant_ref=runtime.demo_merchant_ref,
                occurred_at=occurred_at,
                request_id=context.request_id,
                trace_id=context.trace_id,
            ),
            claim_token=claim_token,
            claimed_at=received_at,
            lease_expires_at=received_at + _EVENT_CLAIM_LEASE,
        )
        if result.outcome is not FeishuFlowOutcome.NEED_INFO or result.case_view is None:
            raise FeishuUnavailable()
        view = result.case_view
        readiness = view.case.readiness
        if (
            readiness.target_role is None
            or readiness.next_question is None
            or readiness.question_reason is None
        ):
            raise FeishuUnavailable()
        card = render_need_info_card(
            NeedInfoCardInput(
                case_id=view.case.case_id,
                case_revision=view.case.case_revision,
                missing_fields=readiness.missing_fields,
                target_role=readiness.target_role,
                completion_ratio=readiness.completion_ratio,
                next_question=readiness.next_question,
                question_reason=readiness.question_reason,
            )
        )
        idempotency_hash = hashlib.sha256(
            f"NEED_INFO\0{view.case.case_id}\0{view.case.case_revision}".encode()
        ).hexdigest()
        runtime.outbound_client.send_interactive_card(
            receive_id=message.chat_id,
            receive_id_type=FeishuReceiveIdType.CHAT_ID,
            card=card,
            idempotency_key=f"opq_{idempotency_hash[:60]}",
        )
        with runtime.store_factory.session() as store:
            store.complete_event(
                callback.header.event_id,
                claim_token=claim_token,
                response={"ok": True},
                case_id=view.case.case_id,
                completed_at=datetime.now(UTC).isoformat(),
            )
    except ReceiptConflict:
        raise FeishuIdempotencyConflict() from None
    except FeishuBindingInProgress:
        _release_claim(runtime, callback.header.event_id, payload_hash, claim_token)
        raise FeishuUnavailable() from None
    except FeishuOutboundError:
        _release_claim(runtime, callback.header.event_id, payload_hash, claim_token)
        raise FeishuUnavailable() from None
    except (OSError, sqlite3.Error):
        _release_claim(runtime, callback.header.event_id, payload_hash, claim_token)
        raise FeishuUnavailable() from None
    except Exception:
        _release_claim(runtime, callback.header.event_id, payload_hash, claim_token)
        raise
    return FeishuCallbackAcknowledgement()


def _release_claim(
    runtime: FeishuRuntime,
    event_id: str,
    payload_hash: str,
    claim_token: str,
) -> None:
    try:
        with runtime.store_factory.session() as store:
            store.release_event(
                event_id,
                payload_hash=payload_hash,
                claim_token=claim_token,
            )
    except (OSError, sqlite3.Error, ReceiptConflict, ValueError):
        pass


@router.post(
    "/card-actions",
    responses=_CALLBACK_PROBLEMS,
    openapi_extra=_CALLBACK_OPENAPI,
)
async def receive_card_action(
    request: Request,
    runtime: Annotated[FeishuRuntime, Depends(get_feishu_runtime)],
) -> None:
    await _verified_payload(request, runtime)
    raise FeishuInvalidCallback()
