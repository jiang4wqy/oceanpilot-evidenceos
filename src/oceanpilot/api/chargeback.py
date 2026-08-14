from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.api.chargeback_schemas import (
    AgentActivityDTO,
    AppealRequest,
    CatalogResponse,
    ChargebackAppealResponse,
    ChargebackAssessmentDTO,
    ChargebackAuditEventDTO,
    ChargebackAuditResponse,
    ChargebackCaseResponse,
    ChargebackDeadlineDTO,
    ChargebackEvidenceItemDTO,
    ChargebackFactsDTO,
    ChargebackPackageResponse,
    ConfirmReasonRequest,
    CreateChargebackRequest,
    LabeledEvidenceDTO,
    MetricsResponse,
    PreventionRequest,
    PreventionResponse,
    SafetyScanRequest,
    SafetyScanResponse,
    SubmitEvidenceRequest,
)
from oceanpilot.application.channels import Delivery, InboundKind, NormalizedInbound
from oceanpilot.application.chargeback_agents import PreventionAgent
from oceanpilot.application.chargeback_appeal import AppealAgent
from oceanpilot.application.chargeback_channel_service import ChargebackChannelService
from oceanpilot.application.chargeback_deadline import DeadlineTracker
from oceanpilot.application.chargeback_packager import PackagerAgent, RepresentmentPackage
from oceanpilot.application.chargeback_ports import ChargebackCaseStore
from oceanpilot.application.chargeback_supervisor import ChargebackSupervisor
from oceanpilot.application.errors import CaseNotFound
from oceanpilot.application.metrics import DecisionMetrics
from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode
from oceanpilot.domain.chargeback_prevention import PreventionSignals
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.domain.evidence_catalog import label_of
from oceanpilot.domain.reason_catalog import reason_label
from oceanpilot.domain.security import assert_no_sensitive_data

router = APIRouter(prefix="/api/v1/chargeback")

# The HTTP API is one channel over the channel-agnostic core: it maps the request
# to a NormalizedInbound, runs the shared ChargebackChannelService, and renders
# the resulting Delivery as JSON. Feishu / other channels reuse the same core.
_CHANNEL = "http"


def get_supervisor(request: Request) -> ChargebackSupervisor:
    return request.app.state.chargeback_supervisor


def get_store(request: Request) -> ChargebackCaseStore:
    return request.app.state.chargeback_store


def get_deadline(request: Request) -> DeadlineTracker:
    return request.app.state.chargeback_deadline


def get_packager(request: Request) -> PackagerAgent:
    return request.app.state.chargeback_packager


def get_appeal(request: Request) -> AppealAgent:
    return request.app.state.chargeback_appeal


def get_prevention(request: Request) -> PreventionAgent:
    return request.app.state.chargeback_prevention


def get_metrics(request: Request) -> DecisionMetrics:
    return request.app.state.chargeback_metrics


def _norm_locale(locale: str) -> str:
    return "en" if locale == "en" else "zh"


def _labeled(
    codes: tuple[ChargebackEvidenceCode, ...], *, locale: str = "zh"
) -> tuple[LabeledEvidenceDTO, ...]:
    return tuple(LabeledEvidenceDTO(code=c.value, label=label_of(c, locale=locale)) for c in codes)


def _package_response(
    case_id: str, package: RepresentmentPackage, *, locale: str = "zh"
) -> ChargebackPackageResponse:
    return ChargebackPackageResponse(
        case_id=case_id,
        reason_code=package.reason_code.value,
        reason_label=reason_label(package.reason_code, locale=locale),
        bank_id=package.bank_id,
        card_network=package.card_network,
        rule_source=package.rule_source,
        scheme_reason_code=package.scheme_reason_code,
        rule_version=package.rule_version,
        source_document=package.source_document,
        source_section=package.source_section,
        required_assertions=package.required_assertions,
        rule_limitation=package.rule_limitation,
        submission_window_days=package.submission_window_days,
        completeness=str(package.completeness),
        ready_to_submit=package.ready_to_submit,
        ordered_evidence=_labeled(package.ordered_evidence, locale=locale),
        missing_evidence=_labeled(package.missing_evidence, locale=locale),
        cover_note=package.cover_note,
        cover_note_source=package.cover_note_source.value,
    )


def get_channel_service(
    supervisor: Annotated[ChargebackSupervisor, Depends(get_supervisor)],
    store: Annotated[ChargebackCaseStore, Depends(get_store)],
    deadline: Annotated[DeadlineTracker, Depends(get_deadline)],
    metrics: Annotated[DecisionMetrics, Depends(get_metrics)],
) -> ChargebackChannelService:
    return ChargebackChannelService(supervisor, store, deadline=deadline, metrics=metrics)


def _response(delivery: Delivery) -> ChargebackCaseResponse:
    assessment = None
    if delivery.assessment is not None:
        a = delivery.assessment
        assessment = ChargebackAssessmentDTO(
            win_likelihood=a.win_likelihood,
            evidence_readiness=a.win_likelihood,
            completeness=a.completeness,
            responsible_team=a.responsible_team,
            requires_human=a.requires_human,
            review_reasons=a.review_reasons,
            explanation=a.explanation,
            explanation_source=a.explanation_source,
            evidence_breakdown=tuple(
                ChargebackEvidenceItemDTO(
                    code=item.code,
                    label=item.label,
                    weight=item.weight,
                    critical=item.critical,
                    present=item.present,
                )
                for item in a.evidence_breakdown
            ),
        )
    deadline = None
    if delivery.deadline is not None:
        d = delivery.deadline
        deadline = ChargebackDeadlineDTO(
            phase=d.phase,
            days_remaining=d.days_remaining,
            deadline_at=d.deadline_at,
            overdue=d.overdue,
        )
    facts = None
    if delivery.facts is not None:
        f = delivery.facts
        facts = ChargebackFactsDTO(
            amount=f.amount,
            currency=f.currency,
            occurred_on=f.occurred_on,
            summary=f.summary,
        )
    return ChargebackCaseResponse(
        case_id=delivery.case_id,
        phase=delivery.phase,
        reason_code=delivery.reason_code,
        reason_confirmed=delivery.reason_confirmed,
        collection_finalized=delivery.collection_finalized,
        collected=delivery.collected,
        next_evidence=delivery.next_evidence,
        question=delivery.question,
        missing=delivery.missing,
        assessment=assessment,
        deadline=deadline,
        facts=facts,
        agent_trace=tuple(
            AgentActivityDTO(agent=a.agent, action=a.action, source=a.source)
            for a in delivery.agent_trace
        ),
    )


@router.post(
    "/cases",
    response_model=ChargebackCaseResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**COMMON_PROBLEMS},
)
def create_case(
    payload: CreateChargebackRequest,
    service: Annotated[ChargebackChannelService, Depends(get_channel_service)],
) -> ChargebackCaseResponse:
    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.OPEN_CASE,
            channel=_CHANNEL,
            description=payload.description,
        )
    )
    return _response(delivery)


@router.post(
    "/cases/{case_id}/confirm",
    response_model=ChargebackCaseResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def confirm_reason(
    case_id: str,
    payload: ConfirmReasonRequest,
    service: Annotated[ChargebackChannelService, Depends(get_channel_service)],
) -> ChargebackCaseResponse:
    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.CONFIRM_REASON,
            channel=_CHANNEL,
            case_id=case_id,
            reason_code=payload.reason_code.value if payload.reason_code else None,
        )
    )
    return _response(delivery)


@router.post(
    "/cases/{case_id}/evidence",
    response_model=ChargebackCaseResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def submit_evidence(
    case_id: str,
    payload: SubmitEvidenceRequest,
    service: Annotated[ChargebackChannelService, Depends(get_channel_service)],
) -> ChargebackCaseResponse:
    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.SUBMIT_EVIDENCE,
            channel=_CHANNEL,
            case_id=case_id,
            evidence_code=payload.evidence_code.value,
        )
    )
    return _response(delivery)


@router.post(
    "/cases/{case_id}/finalize",
    response_model=ChargebackCaseResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def finalize_evidence(
    case_id: str,
    service: Annotated[ChargebackChannelService, Depends(get_channel_service)],
) -> ChargebackCaseResponse:
    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.FINALIZE_EVIDENCE,
            channel=_CHANNEL,
            case_id=case_id,
        )
    )
    return _response(delivery)


@router.get(
    "/cases/{case_id}/package",
    response_model=ChargebackPackageResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def get_package(
    case_id: str,
    store: Annotated[ChargebackCaseStore, Depends(get_store)],
    packager: Annotated[PackagerAgent, Depends(get_packager)],
    bank_id: str | None = None,
    card_network: str | None = None,
    locale: str = "zh",
) -> ChargebackPackageResponse:
    state = store.load(case_id)
    if state is None or state.reason_code is None:
        raise CaseNotFound()
    package = packager.build(
        state.reason_code, state.collected, bank_id=bank_id, card_network=card_network
    )
    return _package_response(case_id, package, locale=_norm_locale(locale))


@router.post(
    "/cases/{case_id}/appeal",
    response_model=ChargebackAppealResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def post_appeal(
    case_id: str,
    payload: AppealRequest,
    store: Annotated[ChargebackCaseStore, Depends(get_store)],
    packager: Annotated[PackagerAgent, Depends(get_packager)],
    appeal: Annotated[AppealAgent, Depends(get_appeal)],
    metrics: Annotated[DecisionMetrics, Depends(get_metrics)],
) -> ChargebackAppealResponse:
    state = store.load(case_id)
    if state is None or state.reason_code is None:
        raise CaseNotFound()
    # AppealRequest already enforces actor_id when human_approved.
    package = packager.build(
        state.reason_code,
        state.collected,
        bank_id=payload.bank_id,
        card_network=payload.card_network,
    )
    outcome = appeal.submit(
        package, human_approved=payload.human_approved, actor_id=payload.actor_id or ""
    )
    metrics.incr("appeal_submitted" if outcome.submitted else "appeal_blocked")
    return ChargebackAppealResponse(
        draft=outcome.draft,
        draft_source=outcome.draft_source.value,
        submitted=outcome.submitted,
        submission_id=outcome.submission_id,
        status=outcome.status,
        blocked_reason=outcome.blocked_reason.value if outcome.blocked_reason else None,
    )


@router.post(
    "/safety/scan",
    response_model=SafetyScanResponse,
    responses={**COMMON_PROBLEMS},
)
def safety_scan(payload: SafetyScanRequest) -> SafetyScanResponse:
    # Runs the same sensitive-data guard used across the system. The input is
    # never echoed back — only the verdict.
    try:
        assert_no_sensitive_data({"text": payload.text})
    except SensitiveDataRejected:
        return SafetyScanResponse(
            accepted=False,
            detail="检出疑似敏感数据（如卡号 / PII），已拦截，不予接收。",
        )
    return SafetyScanResponse(accepted=True, detail="未检出敏感数据。")


@router.get(
    "/catalog",
    response_model=CatalogResponse,
    responses={**COMMON_PROBLEMS},
)
def get_catalog(locale: str = "zh") -> CatalogResponse:
    loc = _norm_locale(locale)
    reasons = tuple(
        LabeledEvidenceDTO(code=r.value, label=reason_label(r, locale=loc))
        for r in DisputeReasonCode
    )
    evidence = tuple(
        LabeledEvidenceDTO(code=c.value, label=label_of(c, locale=loc))
        for c in ChargebackEvidenceCode
    )
    return CatalogResponse(locale=loc, reasons=reasons, evidence=evidence)


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    responses={**COMMON_PROBLEMS},
)
def get_decision_metrics(
    metrics: Annotated[DecisionMetrics, Depends(get_metrics)],
) -> MetricsResponse:
    return MetricsResponse(counts=metrics.snapshot())


@router.post(
    "/prevention/assess",
    response_model=PreventionResponse,
    responses={**COMMON_PROBLEMS},
)
def assess_prevention(
    payload: PreventionRequest,
    agent: Annotated[PreventionAgent, Depends(get_prevention)],
    metrics: Annotated[DecisionMetrics, Depends(get_metrics)],
) -> PreventionResponse:
    signals = PreventionSignals(
        avs_match=payload.avs_match,
        cvv_match=payload.cvv_match,
        three_ds_authenticated=payload.three_ds_authenticated,
        device_ip_match=payload.device_ip_match,
        amount=payload.amount,
        high_risk_mcc=payload.high_risk_mcc,
        cross_border=payload.cross_border,
        shipping_billing_mismatch=payload.shipping_billing_mismatch,
        customer_dispute_history=payload.customer_dispute_history,
        digital_goods=payload.digital_goods,
    )
    outcome = agent.assess(signals)
    a = outcome.assessment
    metrics.incr(f"prevention_risk_{a.risk_level.value}")
    return PreventionResponse(
        risk_level=a.risk_level.value,
        risk_score=str(a.risk_score),
        factors=tuple(factor.value for factor in a.factors),
        recommended_evidence=_labeled(a.recommended_evidence),
        recommend_manual_review=a.recommend_manual_review,
        advice=outcome.advice,
        advice_source=outcome.advice_source.value,
    )


@router.get(
    "/cases/{case_id}/audit",
    response_model=ChargebackAuditResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def get_audit(
    case_id: str,
    store: Annotated[ChargebackCaseStore, Depends(get_store)],
) -> ChargebackAuditResponse:
    if store.load(case_id) is None:
        raise CaseNotFound()
    events = tuple(
        ChargebackAuditEventDTO(
            seq=event.seq,
            event_type=event.event_type,
            detail=event.detail,
            case_revision=event.case_revision,
            occurred_at=event.occurred_at.isoformat(),
        )
        for event in store.audit_trail(case_id)
    )
    return ChargebackAuditResponse(case_id=case_id, events=events)


@router.get(
    "/cases/{case_id}",
    response_model=ChargebackCaseResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def get_case(
    case_id: str,
    service: Annotated[ChargebackChannelService, Depends(get_channel_service)],
) -> ChargebackCaseResponse:
    delivery = service.handle(
        NormalizedInbound(kind=InboundKind.GET_CASE, channel=_CHANNEL, case_id=case_id)
    )
    return _response(delivery)
