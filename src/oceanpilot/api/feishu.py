import json
import sqlite3
from datetime import UTC, datetime
from typing import Final
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from oceanpilot.adapters.feishu.cards import (
    NeedInfoCardInput,
    render_diagnosis_card,
    render_need_info_card,
)
from oceanpilot.adapters.feishu.client import (
    FeishuOutboundClient,
    FeishuOutboundError,
    FeishuReceiveIdType,
)
from oceanpilot.adapters.feishu.security import (
    FeishuRequestVerifier,
    FeishuVerificationError,
)
from oceanpilot.adapters.feishu.store import (
    FeishuCallbackStoreFactory,
    ReceiptConflict,
    ReceiptOutcome,
)
from oceanpilot.api.feishu_schemas import (
    ACTION_SUBMIT_EVIDENCE,
    ALLOWED_CARD_ACTIONS,
    CARD_ACTION_EVENT,
    MESSAGE_RECEIVE_EVENT,
    FeishuActionValue,
    FeishuCardActionEnvelope,
    FeishuMessageEnvelope,
)
from oceanpilot.application.feishu_models import (
    CaseBindingMismatch,
    ConfirmationRequest,
    EvidenceAnswer,
    FeishuOutcomeKind,
    MessageEvent,
    OrchestrationOutcome,
    UnboundChat,
)
from oceanpilot.application.feishu_orchestrator import FeishuOrchestrator
from oceanpilot.domain.enums import EvidenceCode

router = APIRouter(prefix="/api/v1/integrations/feishu")

MAX_BODY_BYTES: Final = 64 * 1024
_JSON_MEDIA_TYPES: Final = frozenset({"application/json"})

_ERR_UNAVAILABLE = {"code": 503, "msg": "feishu integration unavailable"}
_ERR_MEDIA_TYPE = {"code": 415, "msg": "unsupported media type"}
_ERR_TOO_LARGE = {"code": 413, "msg": "payload too large"}
_ERR_VERIFICATION = {"code": 401, "msg": "verification failed"}
_ERR_INVALID = {"code": 400, "msg": "invalid callback"}
_ERR_CONFLICT = {"code": 409, "msg": "conflict"}
_ERR_INTERNAL = {"code": 500, "msg": "internal error"}
_ACK = {"code": 0}


def _reply(status: int, body: dict[str, object]) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)


def _now_text() -> str:
    return datetime.now(UTC).isoformat()


def _content_type_ok(header: str | None) -> bool:
    if header is None:
        return False
    return header.split(";", 1)[0].strip().lower() in _JSON_MEDIA_TYPES


async def _read_capped(request: Request, cap: int) -> bytes | None:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > cap:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _extract_message_text(content: str | None) -> str:
    if not content:
        return ""
    try:
        decoded = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return ""
    if isinstance(decoded, dict):
        text = decoded.get("text")
        if isinstance(text, str):
            return text
    return ""


def _need_info_card(outcome: OrchestrationOutcome) -> tuple[dict[str, object], str] | None:
    view = outcome.case_view
    if view is None:
        return None
    readiness = view.case.readiness
    if (
        readiness.next_question is None
        or readiness.target_role is None
        or not readiness.missing_fields
    ):
        return None
    card = render_need_info_card(
        NeedInfoCardInput(
            case_id=view.case.case_id,
            case_revision=view.case.case_revision,
            missing_fields=tuple(readiness.missing_fields),
            target_role=readiness.target_role,
            next_question=readiness.next_question,
            question_reason=readiness.question_reason or readiness.next_question,
        )
    )
    return card, f"ni-{view.case.case_id}-{view.case.case_revision}"


def _card_for(outcome: OrchestrationOutcome) -> tuple[dict[str, object], str] | None:
    if outcome.kind is FeishuOutcomeKind.NEED_INFO:
        return _need_info_card(outcome)
    if (
        outcome.kind
        in (
            FeishuOutcomeKind.DIAGNOSED,
            FeishuOutcomeKind.ALREADY_DIAGNOSED,
            FeishuOutcomeKind.CONFIRMED,
        )
        and outcome.diagnosis_view is not None
    ):
        card = render_diagnosis_card(outcome.diagnosis_view)
        return card, f"dx-{outcome.diagnosis_view.diagnosis.diagnosis_id}"
    return None


def _send_card(
    client: FeishuOutboundClient,
    chat_id: str,
    outcome: OrchestrationOutcome,
) -> None:
    rendered = _card_for(outcome)
    if rendered is None:
        return
    card, idempotency_key = rendered
    try:
        client.send_interactive_card(
            receive_id=chat_id,
            receive_id_type=FeishuReceiveIdType.CHAT_ID,
            card=card,
            idempotency_key=idempotency_key,
        )
    except FeishuOutboundError:
        return


def _case_id_of(outcome: OrchestrationOutcome) -> str | None:
    if outcome.case_view is not None:
        return outcome.case_view.case.case_id
    if outcome.diagnosis_view is not None:
        return outcome.diagnosis_view.case_id
    return None


def _summary(outcome: OrchestrationOutcome, *, case_id: str) -> dict[str, object]:
    summary: dict[str, object] = {"outcome": outcome.kind.value, "case_id": case_id}
    if outcome.diagnosis_view is not None:
        summary["diagnosis_id"] = outcome.diagnosis_view.diagnosis.diagnosis_id
    return summary


def _process_message(
    orchestrator: FeishuOrchestrator,
    store_factory: FeishuCallbackStoreFactory,
    client: FeishuOutboundClient,
    envelope: FeishuMessageEnvelope,
) -> JSONResponse:
    event_id = envelope.header.event_id
    if not event_id:
        return _reply(400, _ERR_INVALID)
    sender = envelope.event.sender
    if sender is not None and sender.sender_type == "app":
        return _reply(200, _ACK)
    message = envelope.event.message
    text = _extract_message_text(message.content)

    with store_factory.session() as store:
        claim = store.claim_event(event_id, created_at=_now_text())
        if claim.outcome is ReceiptOutcome.REPLAY:
            return _reply(200, claim.response or _ACK)
        if claim.outcome is ReceiptOutcome.IN_PROGRESS:
            return _reply(200, _ACK)
        outcome = orchestrator.handle_message(
            store, MessageEvent(chat_id=message.chat_id, text=text)
        )
        case_id = _case_id_of(outcome)
        if case_id is None:
            return _reply(200, _ACK)
        summary = _summary(outcome, case_id=case_id)
        store.complete_event(event_id, response=summary, case_id=case_id, completed_at=_now_text())

    _send_card(client, message.chat_id, outcome)
    return _reply(200, summary)


def _process_evidence(
    orchestrator: FeishuOrchestrator,
    store: object,
    envelope: FeishuCardActionEnvelope,
    action_id: str,
) -> JSONResponse | tuple[JSONResponse, OrchestrationOutcome, str]:
    value = envelope.event.action.value
    context = envelope.event.context
    chat_id = context.open_chat_id if context is not None else None
    if (
        not chat_id
        or not value.case_id
        or not value.evidence_id
        or value.evidence_code is None
        or value.availability is None
        or not value.source_ref
    ):
        return _reply(400, _ERR_INVALID)
    observed_at = _parse_optional_datetime(value.observed_at)
    typed_value = _resolve_typed_value(value)
    answer = EvidenceAnswer(
        chat_id=chat_id,
        case_id=value.case_id,
        actor_id=_actor_of(envelope) or "ou_unknown",
        evidence_id=value.evidence_id,
        evidence_code=value.evidence_code,
        availability=value.availability,
        source_ref=value.source_ref,
        typed_value=typed_value,
        observed_at=observed_at,
    )
    claim = store.claim_event(action_id, created_at=_now_text())
    if claim.outcome is ReceiptOutcome.REPLAY:
        return _reply(200, claim.response or _ACK)
    if claim.outcome is ReceiptOutcome.IN_PROGRESS:
        return _reply(200, _ACK)
    outcome = orchestrator.handle_evidence(store, answer)
    case_id = _case_id_of(outcome) or value.case_id
    summary = _summary(outcome, case_id=case_id)
    store.complete_event(action_id, response=summary, case_id=case_id, completed_at=_now_text())
    return _reply(200, summary), outcome, chat_id


def _process_confirmation(
    orchestrator: FeishuOrchestrator,
    store: object,
    envelope: FeishuCardActionEnvelope,
    action_id: str,
) -> JSONResponse | tuple[JSONResponse, OrchestrationOutcome, str]:
    value = envelope.event.action.value
    context = envelope.event.context
    chat_id = context.open_chat_id if context is not None else None
    actor_id = _actor_of(envelope)
    if not chat_id or not value.case_id or not value.diagnosis_id or not actor_id:
        return _reply(400, _ERR_INVALID)
    claim = store.claim_action(action_id, created_at=_now_text())
    if claim.outcome is ReceiptOutcome.REPLAY:
        return _reply(200, claim.response or _ACK)
    if claim.outcome is ReceiptOutcome.IN_PROGRESS:
        return _reply(200, _ACK)
    outcome = orchestrator.evaluate_confirmation(
        store,
        ConfirmationRequest(
            chat_id=chat_id,
            case_id=value.case_id,
            diagnosis_id=value.diagnosis_id,
            actor_id=actor_id,
        ),
    )
    summary = _summary(outcome, case_id=value.case_id)
    if outcome.kind is FeishuOutcomeKind.CONFIRMED:
        try:
            store.commit_confirmation(
                action_id=action_id,
                approval_id=str(uuid4()),
                response=summary,
                case_id=value.case_id,
                diagnosis_id=value.diagnosis_id,
                actor_id=actor_id,
                result="CONFIRMED",
                occurred_at=_now_text(),
            )
        except ReceiptConflict:
            return _reply(409, _ERR_CONFLICT)
        return _reply(200, summary), outcome, chat_id
    store.complete_action(
        action_id,
        response=summary,
        case_id=value.case_id,
        diagnosis_id=value.diagnosis_id,
        actor_id=actor_id,
        completed_at=_now_text(),
    )
    return _reply(200, summary)


def _actor_of(envelope: FeishuCardActionEnvelope) -> str | None:
    operator = envelope.event.operator
    return operator.open_id if operator is not None else None


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _resolve_typed_value(value: FeishuActionValue) -> str | bool | datetime | None:
    if value.evidence_code is EvidenceCode.TRANSACTION_OCCURRED_AT and isinstance(
        value.typed_value, str
    ):
        return _parse_optional_datetime(value.typed_value)
    return value.typed_value


def _process_card_action(
    orchestrator: FeishuOrchestrator,
    store_factory: FeishuCallbackStoreFactory,
    client: FeishuOutboundClient,
    envelope: FeishuCardActionEnvelope,
) -> JSONResponse:
    action_id = envelope.header.event_id
    if not action_id:
        return _reply(400, _ERR_INVALID)
    action_kind = envelope.event.action.value.action
    if action_kind not in ALLOWED_CARD_ACTIONS:
        return _reply(400, _ERR_INVALID)

    with store_factory.session() as store:
        try:
            if action_kind == ACTION_SUBMIT_EVIDENCE:
                processed = _process_evidence(orchestrator, store, envelope, action_id)
            else:
                processed = _process_confirmation(orchestrator, store, envelope, action_id)
        except (UnboundChat, CaseBindingMismatch):
            return _reply(400, _ERR_INVALID)

    if isinstance(processed, tuple):
        response, outcome, chat_id = processed
        _send_card(client, chat_id, outcome)
        return response
    return processed


async def _handle(request: Request, mode: str) -> JSONResponse:
    state = request.app.state
    orchestrator = getattr(state, "feishu_orchestrator", None)
    store_factory = getattr(state, "feishu_store_factory", None)
    verifier: FeishuRequestVerifier | None = getattr(state, "feishu_verifier", None)
    client = getattr(state, "feishu_client", None)
    if orchestrator is None or store_factory is None or verifier is None or client is None:
        return _reply(503, _ERR_UNAVAILABLE)

    if not _content_type_ok(request.headers.get("content-type")):
        return _reply(415, _ERR_MEDIA_TYPE)
    length = request.headers.get("content-length")
    if length is None or not length.isdigit() or int(length) > MAX_BODY_BYTES:
        return _reply(413, _ERR_TOO_LARGE)
    raw = await _read_capped(request, MAX_BODY_BYTES)
    if raw is None:
        return _reply(413, _ERR_TOO_LARGE)

    try:
        payload = verifier.verify(dict(request.headers), raw)
    except FeishuVerificationError:
        return _reply(401, _ERR_VERIFICATION)

    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not isinstance(challenge, str) or not challenge:
            return _reply(400, _ERR_INVALID)
        return _reply(200, {"challenge": challenge})

    try:
        if mode == "event":
            envelope = FeishuMessageEnvelope.model_validate(payload)
            if envelope.header.event_type != MESSAGE_RECEIVE_EVENT:
                return _reply(200, _ACK)
            return await run_in_threadpool(
                _process_message, orchestrator, store_factory, client, envelope
            )
        card = FeishuCardActionEnvelope.model_validate(payload)
        if card.header.event_type not in (CARD_ACTION_EVENT, None):
            return _reply(400, _ERR_INVALID)
        return await run_in_threadpool(
            _process_card_action, orchestrator, store_factory, client, card
        )
    except ValidationError:
        return _reply(400, _ERR_INVALID)
    except sqlite3.Error:
        return _reply(503, _ERR_UNAVAILABLE)
    except Exception:  # noqa: BLE001
        return _reply(500, _ERR_INTERNAL)


@router.post("/events")
async def feishu_events(request: Request) -> JSONResponse:
    return await _handle(request, "event")


@router.post("/card-actions")
async def feishu_card_actions(request: Request) -> JSONResponse:
    return await _handle(request, "card")
