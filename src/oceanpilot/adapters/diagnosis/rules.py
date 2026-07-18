from dataclasses import dataclass
from decimal import Decimal
from typing import Final, cast

from oceanpilot.domain.diagnosis import calculate_confidence
from oceanpilot.domain.enums import (
    EvidenceCode,
    Priority,
    ResponsibleTeam,
    ReviewReason,
)
from oceanpilot.domain.models import (
    ActiveEvidenceView,
    DiagnosisDraft,
    EvidenceItem,
    HypothesisDraft,
    MerchantSuccessCase,
    RoutingDecision,
    TicketDraft,
)


@dataclass(frozen=True)
class EvidencePredicate:
    evidence_code: EvidenceCode
    allowed_values: frozenset[str]


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    cause_code: str
    required_predicates: tuple[EvidencePredicate, ...]
    responsible_team: ResponsibleTeam
    priority: Priority
    forced_review_reasons: frozenset[ReviewReason]
    next_verification_action: str
    explanation: str
    routing_reason: str
    ticket_title: str


RULES: Final[tuple[RuleDefinition, ...]] = (
    RuleDefinition(
        rule_id="THREEDS_INCOMPLETE_V1",
        cause_code="THREEDS_AUTH_OR_CALLBACK_INCOMPLETE",
        required_predicates=(
            EvidencePredicate(
                EvidenceCode.SYMPTOM_STATUS,
                frozenset({"PENDING", "FAILED"}),
            ),
            EvidencePredicate(
                EvidenceCode.AUTHENTICATION_STATUS,
                frozenset({"REQUIRED", "CHALLENGE_PENDING", "FAILED"}),
            ),
            EvidencePredicate(
                EvidenceCode.CALLBACK_DELIVERY_STATUS,
                frozenset({"NOT_RECEIVED", "FAILED"}),
            ),
        ),
        responsible_team=ResponsibleTeam.TECHNICAL_SUPPORT,
        priority=Priority.MEDIUM,
        forced_review_reasons=frozenset(),
        next_verification_action="核对认证结果与服务器回调接收链，不自动重试付款",
        explanation="交易状态、认证状态与回调状态同时命中未完成规则，需核对认证与回调链路。",
        routing_reason="认证或回调链路需要技术支持复核。",
        ticket_title="复核 3DS 认证与回调链路",
    ),
    RuleDefinition(
        rule_id="RISK_DECLINE_V1",
        cause_code="RISK_DECLINE_REQUIRES_REVIEW",
        required_predicates=(
            EvidencePredicate(
                EvidenceCode.SYMPTOM_STATUS,
                frozenset({"DECLINED", "FAILED"}),
            ),
            EvidencePredicate(
                EvidenceCode.RISK_DECISION_CODE,
                frozenset({"RISK_DECLINE"}),
            ),
        ),
        responsible_team=ResponsibleTeam.RISK,
        priority=Priority.HIGH,
        forced_review_reasons=frozenset({ReviewReason.RISK_DECISION}),
        next_verification_action="由风控人员复核决策依据，不自动放行",
        explanation="交易状态与 RISK_DECLINE 决策码同时命中风险复核规则。",
        routing_reason="风险拒绝需要风控团队人工复核。",
        ticket_title="复核风险拒绝决策",
    ),
    RuleDefinition(
        rule_id="CONFIG_MISMATCH_MERCHANT_V1",
        cause_code="PAYMENT_CONFIGURATION_MISMATCH",
        required_predicates=(
            EvidencePredicate(
                EvidenceCode.SYMPTOM_STATUS,
                frozenset({"PENDING", "FAILED"}),
            ),
            EvidencePredicate(
                EvidenceCode.CONTEXT_ENVIRONMENT,
                frozenset({"PROD", "SANDBOX"}),
            ),
            EvidencePredicate(
                EvidenceCode.PAYMENT_METHOD,
                frozenset({
                    "CARD",
                    "APPLE_PAY",
                    "GOOGLE_PAY",
                    "KLARNA",
                    "LOCAL_PAYMENT",
                    "OTHER",
                }),
            ),
            EvidencePredicate(
                EvidenceCode.CONFIGURATION_CHECK_RESULT,
                frozenset({"MERCHANT_SIDE_MISMATCH"}),
            ),
        ),
        responsible_team=ResponsibleTeam.TECHNICAL_SUPPORT,
        priority=Priority.MEDIUM,
        forced_review_reasons=frozenset(),
        next_verification_action="生成商户侧环境/方式配置核对清单，不自动修改配置",
        explanation="环境、支付方式与配置检查结果命中商户侧配置不匹配规则。",
        routing_reason="商户侧支付配置需要技术支持核对。",
        ticket_title="核对商户侧支付配置",
    ),
    RuleDefinition(
        rule_id="CONFIG_MISMATCH_PSP_V1",
        cause_code="PAYMENT_CONFIGURATION_MISMATCH",
        required_predicates=(
            EvidencePredicate(
                EvidenceCode.SYMPTOM_STATUS,
                frozenset({"PENDING", "FAILED"}),
            ),
            EvidencePredicate(
                EvidenceCode.CONTEXT_ENVIRONMENT,
                frozenset({"PROD", "SANDBOX"}),
            ),
            EvidencePredicate(
                EvidenceCode.PAYMENT_METHOD,
                frozenset({
                    "CARD",
                    "APPLE_PAY",
                    "GOOGLE_PAY",
                    "KLARNA",
                    "LOCAL_PAYMENT",
                    "OTHER",
                }),
            ),
            EvidencePredicate(
                EvidenceCode.CONFIGURATION_CHECK_RESULT,
                frozenset({"PSP_PROFILE_MISMATCH"}),
            ),
        ),
        responsible_team=ResponsibleTeam.PSP_SUPPORT,
        priority=Priority.MEDIUM,
        forced_review_reasons=frozenset(),
        next_verification_action="生成 PSP 资料核对草稿，不触发生产变更",
        explanation="环境、支付方式与配置检查结果命中 PSP 侧资料配置不匹配规则。",
        routing_reason="PSP 侧资料配置需要支持团队核对。",
        ticket_title="核对 PSP 侧资料配置",
    ),
)


def _matches(rule: RuleDefinition, view: ActiveEvidenceView) -> bool:
    return all(
        (selected := view.slots[predicate.evidence_code].selected_evidence) is not None
        and selected.typed_value in predicate.allowed_values
        for predicate in rule.required_predicates
    )


def _human_only(reason: ReviewReason) -> DiagnosisDraft:
    return DiagnosisDraft(
        hypotheses=(),
        routing_decision=None,
        ticket_draft=None,
        requires_human=True,
        review_reasons=frozenset({reason}),
    )


class RuleDiagnosisEngine:
    def evaluate(
        self,
        case: MerchantSuccessCase,
        view: ActiveEvidenceView,
        *,
        policy_version: str,
    ) -> DiagnosisDraft:
        if ReviewReason.CONFLICTING_EVIDENCE in view.review_reasons:
            return _human_only(ReviewReason.CONFLICTING_EVIDENCE)

        matched = tuple(rule for rule in RULES if _matches(rule, view))
        if not matched:
            return _human_only(ReviewReason.POLICY_GAP)
        if len(matched) > 1:
            return _human_only(ReviewReason.CONFLICTING_EVIDENCE)

        rule = matched[0]
        predicate_evidence = tuple(
            cast(
                EvidenceItem,
                view.slots[predicate.evidence_code].selected_evidence,
            )
            for predicate in rule.required_predicates
        )
        evidence_by_id = {item.evidence_id: item for item in predicate_evidence}
        evidence_refs = tuple(sorted(evidence_by_id))
        decisive_evidence = tuple(evidence_by_id[evidence_id] for evidence_id in evidence_refs)
        confidence = calculate_confidence(
            decisive_evidence,
            required_coverage=Decimal("1"),
            consistency=Decimal("1"),
        )
        review_reasons = confidence.review_reasons | rule.forced_review_reasons
        requires_human = bool(review_reasons)
        hypothesis = HypothesisDraft(
            cause_code=rule.cause_code,
            explanation=rule.explanation,
            evidence_refs=evidence_refs,
            confidence_score=confidence.display_score,
            confidence_method="HEURISTIC_V1",
            next_verification_action=rule.next_verification_action,
            rule_id=rule.rule_id,
        )
        route = RoutingDecision(
            responsible_team=rule.responsible_team,
            priority=rule.priority,
            reason=rule.routing_reason,
            evidence_refs=evidence_refs,
            requires_human=requires_human,
            review_reasons=review_reasons,
        )
        evidence_summary = tuple(
            f"{predicate.evidence_code.value}={item.typed_value}"
            for predicate, item in zip(
                rule.required_predicates,
                predicate_evidence,
                strict=True,
            )
        )
        ticket = TicketDraft(
            title=rule.ticket_title,
            summary=rule.explanation,
            evidence_summary=evidence_summary,
            missing_material=(),
            hypotheses=(hypothesis,),
            next_action=rule.next_verification_action,
            responsible_team=route.responsible_team,
            synthetic=case.synthetic,
        )
        return DiagnosisDraft(
            hypotheses=(hypothesis,),
            routing_decision=route,
            ticket_draft=ticket,
            requires_human=requires_human,
            review_reasons=review_reasons,
        )
