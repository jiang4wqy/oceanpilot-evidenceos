import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from oceanpilot.adapters.feishu.cards import (
    NeedInfoCardInput,
    render_diagnosis_card,
    render_need_info_card,
)
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
    parse_feishu_evidence_action,
    parse_feishu_message_event,
)
from oceanpilot.application.feishu_models import (
    FeishuEvidenceSubmission,
    FeishuFlowOutcome,
    FeishuIncident,
)
from oceanpilot.application.feishu_orchestrator import (
    FeishuBindingInProgress,
    FeishuEvidenceStale,
    FeishuUnexpectedEvidence,
    feishu_evidence_id,
    feishu_evidence_values,
    next_feishu_evidence_code,
)
from oceanpilot.domain.enums import EvidenceCode, TargetRole
from oceanpilot.domain.models import CaseView, DiagnosisView

router = APIRouter(prefix="/api/v1/feishu")
_MAX_CALLBACK_BYTES = 65_536
_EVENT_CLAIM_LEASE = timedelta(seconds=30)
_ACTION_CLAIM_LEASE = timedelta(seconds=30)

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
        if len(declared) > 20 or not declared.isascii() or not declared.isdecimal():
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


def _need_info_card(view: CaseView) -> dict[str, object]:
    readiness = view.case.readiness
    evidence_code = next_feishu_evidence_code(view)
    supporting_questions = {
        EvidenceCode.AUTHENTICATION_STATUS: (
            "请确认这笔交易的 3DS 认证状态。",
            "认证状态用于判断 3DS 流程是否完成。",
        ),
        EvidenceCode.CALLBACK_DELIVERY_STATUS: (
            "请确认支付结果回调是否送达。",
            "回调状态用于区分认证未完成和通知链路异常。",
        ),
        EvidenceCode.RISK_DECISION_CODE: (
            "请确认这笔交易的风控决定码。",
            "决定码用于验证拒绝是否来自风控策略。",
        ),
    }
    if evidence_code is None:
        raise FeishuUnavailable()
    if evidence_code in supporting_questions:
        question, reason = supporting_questions[evidence_code]
        missing_fields = (evidence_code.value,)
    else:
        if readiness.next_question is None or readiness.question_reason is None:
            raise FeishuUnavailable()
        question = readiness.next_question
        reason = readiness.question_reason
        missing_fields = readiness.missing_fields
    return render_need_info_card(
        NeedInfoCardInput(
            case_id=view.case.case_id,
            case_revision=view.case.case_revision,
            evidence_code=evidence_code,
            missing_fields=missing_fields,
            target_role=readiness.target_role or TargetRole.MERCHANT_TECH,
            completion_ratio=readiness.completion_ratio,
            next_question=question,
            question_reason=reason,
        )
    )


def _send_need_info_card(runtime: FeishuRuntime, chat_id: str, view: CaseView) -> None:
    runtime.outbound_client.send_interactive_card(
        receive_id=chat_id,
        receive_id_type=FeishuReceiveIdType.CHAT_ID,
        card=_need_info_card(view),
        idempotency_key=_need_info_key(view.case.case_id, view.case.case_revision),
    )


def _need_info_key(case_id: str, case_revision: int) -> str:
    digest = hashlib.sha256(f"NEED_INFO\0{case_id}\0{case_revision}".encode()).hexdigest()
    return f"opq_{digest[:60]}"


def _diagnosis_key(view: DiagnosisView) -> str:
    digest = hashlib.sha256(
        (f"DIAGNOSIS_CARD_V1\0{view.case_id}\0{view.diagnosis.diagnosis_id}").encode()
    ).hexdigest()
    return f"opd_{digest[:60]}"


def _send_diagnosis_card(
    runtime: FeishuRuntime,
    chat_id: str,
    view: DiagnosisView,
) -> None:
    runtime.outbound_client.send_interactive_card(
        receive_id=chat_id,
        receive_id_type=FeishuReceiveIdType.CHAT_ID,
        card=render_diagnosis_card(view),
        idempotency_key=_diagnosis_key(view),
    )


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
        _send_need_info_card(runtime, message.chat_id, view)
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
) -> FeishuCallbackAcknowledgement:
    payload, raw_body = await _verified_payload(request, runtime)
    try:
        callback = parse_feishu_evidence_action(payload)
    except (TypeError, ValidationError):
        raise FeishuInvalidCallback() from None
    if not hmac.compare_digest(
        callback.header.app_id.encode(),
        runtime.app_id.encode(),
    ):
        raise FeishuCallbackUnauthorized()
    if runtime.demo_chat_id is None:
        raise FeishuUnavailable()
    if not hmac.compare_digest(
        callback.event.context.open_chat_id.encode(),
        runtime.demo_chat_id.encode(),
    ):
        return FeishuCallbackAcknowledgement()

    action = callback.event.action.value
    received_at = datetime.now(UTC)
    claim_token = secrets.token_hex(32)
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    try:
        with runtime.store_factory.session() as store:
            receipt = store.claim_evidence_action(
                callback.header.event_id,
                payload_hash=payload_hash,
                claim_token=claim_token,
                now=received_at.isoformat(),
                lease_expires_at=(received_at + _ACTION_CLAIM_LEASE).isoformat(),
            )
    except ReceiptConflict:
        raise FeishuIdempotencyConflict() from None
    except (OSError, sqlite3.Error, ValueError):
        raise FeishuUnavailable() from None
    if receipt.outcome is ReceiptOutcome.IN_PROGRESS:
        raise FeishuUnavailable()
    if receipt.outcome is ReceiptOutcome.REPLAY:
        return FeishuCallbackAcknowledgement()

    typed_value = action.typed_value
    if action.evidence_code is EvidenceCode.TRANSACTION_OCCURRED_AT:
        if typed_value != feishu_evidence_values(action.evidence_code)[0]:
            _release_evidence_action(
                runtime,
                callback.header.event_id,
                payload_hash,
                claim_token,
            )
            raise FeishuInvalidCallback()
        try:
            typed_value = datetime.fromisoformat(typed_value.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            _release_evidence_action(
                runtime,
                callback.header.event_id,
                payload_hash,
                claim_token,
            )
            raise FeishuInvalidCallback() from None
        if typed_value.tzinfo is None or typed_value.utcoffset() is None:
            _release_evidence_action(
                runtime,
                callback.header.event_id,
                payload_hash,
                claim_token,
            )
            raise FeishuInvalidCallback()

    context = request.state.request_context
    evidence_id = feishu_evidence_id(
        action.case_id,
        action.case_revision,
        action.evidence_code,
    )
    try:
        result = runtime.orchestrator.submit_evidence(
            FeishuEvidenceSubmission(
                event_id=callback.header.event_id,
                case_id=action.case_id,
                expected_case_revision=action.case_revision,
                evidence_code=action.evidence_code,
                availability=action.availability,
                typed_value=typed_value,
                request_id=context.request_id,
                trace_id=context.trace_id,
            )
        )
        if result.outcome is FeishuFlowOutcome.NEED_INFO and result.case_view is not None:
            _send_need_info_card(
                runtime,
                callback.event.context.open_chat_id,
                result.case_view,
            )
        elif result.outcome is FeishuFlowOutcome.DIAGNOSIS and result.diagnosis is not None:
            _send_diagnosis_card(
                runtime,
                callback.event.context.open_chat_id,
                result.diagnosis,
            )
        else:
            raise FeishuUnavailable()
        with runtime.store_factory.session() as store:
            store.complete_evidence_action(
                callback.header.event_id,
                claim_token=claim_token,
                response={"ok": True},
                case_id=action.case_id,
                evidence_id=evidence_id,
                completed_at=datetime.now(UTC).isoformat(),
            )
    except FeishuEvidenceStale as stale:
        try:
            _send_need_info_card(
                runtime,
                callback.event.context.open_chat_id,
                stale.case_view,
            )
            with runtime.store_factory.session() as store:
                store.complete_evidence_action(
                    callback.header.event_id,
                    claim_token=claim_token,
                    response={"ok": True},
                    case_id=action.case_id,
                    evidence_id=evidence_id,
                    completed_at=datetime.now(UTC).isoformat(),
                )
        except ReceiptConflict:
            raise FeishuIdempotencyConflict() from None
        except FeishuOutboundError:
            _release_evidence_action(
                runtime,
                callback.header.event_id,
                payload_hash,
                claim_token,
            )
            raise FeishuUnavailable() from None
        except (OSError, sqlite3.Error):
            _release_evidence_action(
                runtime,
                callback.header.event_id,
                payload_hash,
                claim_token,
            )
            raise FeishuUnavailable() from None
    except FeishuUnexpectedEvidence:
        _release_evidence_action(
            runtime,
            callback.header.event_id,
            payload_hash,
            claim_token,
        )
        raise FeishuInvalidCallback() from None
    except ReceiptConflict:
        raise FeishuIdempotencyConflict() from None
    except FeishuOutboundError:
        _release_evidence_action(
            runtime,
            callback.header.event_id,
            payload_hash,
            claim_token,
        )
        raise FeishuUnavailable() from None
    except (OSError, sqlite3.Error):
        _release_evidence_action(
            runtime,
            callback.header.event_id,
            payload_hash,
            claim_token,
        )
        raise FeishuUnavailable() from None
    except Exception:
        _release_evidence_action(
            runtime,
            callback.header.event_id,
            payload_hash,
            claim_token,
        )
        raise
    return FeishuCallbackAcknowledgement()


def _release_evidence_action(
    runtime: FeishuRuntime,
    action_id: str,
    payload_hash: str,
    claim_token: str,
) -> None:
    try:
        with runtime.store_factory.session() as store:
            store.release_evidence_action(
                action_id,
                payload_hash=payload_hash,
                claim_token=claim_token,
            )
    except (OSError, sqlite3.Error, ReceiptConflict, ValueError):
        pass
