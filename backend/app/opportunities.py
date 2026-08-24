import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, Field
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.gigachat import GigaChatGateway
from app.models import (
    BuyingSignalType,
    Company,
    CompanyBuyingSignal,
    CompanyNegativeSignal,
    CompanyPain,
    DealStatus,
    DealStatusHistory,
    Evidence,
    IcpProfile,
    IcpRule,
    NegativeSignalType,
    OpportunityEvidence,
    PainType,
    Person,
    PersonStatus,
    PromptVersion,
    SalesOpportunity,
    SalesOpportunityFactor,
    SalesPlaybook,
    ScoreCalculation,
    ScoreWeightProfile,
    ServiceCatalog,
    SolutionFitRule,
)

IMPACT_VALUES = {"low": 0.35, "medium": 0.65, "high": 1.0}
STATUS_VALUES = {"confirmed": 1.0, "probable": 0.7, "unknown": 0.0}
DEFAULT_WEIGHTS = {"icp": 0.30, "pain": 0.25, "intent": 0.25, "solution": 0.20}
SCORE_VERSION = "sales-v1"


class IcpMatch(BaseModel):
    rule_id: str
    matched: bool | None
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=100)
    status: Literal["confirmed", "probable", "unknown"]
    reasoning_summary: str


class PainMatch(BaseModel):
    pain_type_id: str
    impact: Literal["low", "medium", "high"]
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=100)
    status: Literal["confirmed", "probable", "unknown"]
    reasoning_summary: str
    qualification_questions: list[str] = Field(default_factory=list)


class SignalMatch(BaseModel):
    signal_type_id: str
    observed_at: datetime
    evidence_ids: list[str] = Field(min_length=1)
    confidence: int = Field(ge=0, le=100)
    status: Literal["confirmed", "probable"]
    reasoning_summary: str


class ServiceClassification(BaseModel):
    service_id: str
    summary: str
    icp_matches: list[IcpMatch]
    pains: list[PainMatch]
    buying_signals: list[SignalMatch]
    negative_signals: list[SignalMatch]


class ClassificationResult(BaseModel):
    company_id: str
    services: list[ServiceClassification]


class ProofPoint(BaseModel):
    statement: str
    evidence_ids: list[str] = Field(min_length=1)


class ObjectionAnswer(BaseModel):
    objection: str
    response: str


class PlaybookResult(BaseModel):
    call_reason: str
    product_to_offer: str
    decision_maker_role: str
    pitch_30_seconds: str
    proof_points: list[ProofPoint] = Field(max_length=3)
    first_question: str
    discovery_questions: list[str]
    objections: list[ObjectionAnswer]
    unknowns: list[str]
    next_action: str
    evidence_ids: list[str]


@dataclass
class Factor:
    dimension: str
    rule_type: str
    rule_id: str | None
    raw_value: float
    weighted_value: float
    status: str
    confidence: int
    explanation: str
    evidence_id: str | None


@dataclass
class Scores:
    icp: float
    pain: float
    intent: float
    solution: float
    total: float
    completeness: float
    evidence_confidence: float
    factors: list[Factor]


def time_decay(observed_at: datetime, decay_days: int, now: datetime) -> float:
    observed = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=UTC)
    age_days = max(0.0, (now - observed).total_seconds() / 86400)
    return float(0.5 ** (age_days / max(decay_days, 1)))


def geometric_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-6):
        raise ValueError("Сумма весов Sales Opportunity должна равняться 1")
    if any(scores[key] <= 0 for key in weights):
        return 0.0
    value = 100.0
    for key, weight in weights.items():
        value *= (scores[key] / 100.0) ** weight
    return round(min(100.0, max(0.0, value)), 2)


def calculate_scores(
    classification: ServiceClassification,
    icp_rules: list[IcpRule],
    pain_types: dict[str, PainType],
    buying_types: dict[str, BuyingSignalType],
    negative_types: dict[str, NegativeSignalType],
    solution_rules: list[SolutionFitRule],
    weights: dict[str, float],
    evidence_confidence: dict[str, int],
    has_confirmed_lpr: bool,
    now: datetime,
) -> Scores:
    factors: list[Factor] = []
    confidences: list[float] = []
    known = 0
    total_configured = len(icp_rules) + len(pain_types) + len(buying_types) + len(negative_types)
    icp_matches = {item.rule_id: item for item in classification.icp_matches}
    icp_numerator = 0.0
    icp_denominator = 0.0
    hard_excluded = False
    for icp_rule in icp_rules:
        icp_match = icp_matches.get(icp_rule.id)
        if not icp_match or icp_match.status == "unknown" or icp_match.matched is None:
            continue
        known += 1
        raw = 100.0 if icp_match.matched else 0.0
        hard_excluded = hard_excluded or (icp_rule.is_exclusion and icp_match.matched)
        icp_numerator += raw * icp_rule.weight
        icp_denominator += icp_rule.weight
        evidence_id = icp_match.evidence_ids[0] if icp_match.evidence_ids else None
        factors.append(
            Factor(
                "icp",
                "icp_rule",
                icp_rule.id,
                raw,
                raw * icp_rule.weight,
                icp_match.status,
                icp_match.confidence,
                icp_match.reasoning_summary,
                evidence_id,
            )
        )
        if evidence_id:
            confidences.append(evidence_confidence[evidence_id] * icp_match.confidence / 100)
    icp = 0.0 if hard_excluded else (icp_numerator / icp_denominator if icp_denominator else 0.0)

    pain_numerator = 0.0
    pain_denominator = 0.0
    pain_by_type: dict[str, PainMatch] = {}
    for pain_match in classification.pains:
        pain_type = pain_types.get(pain_match.pain_type_id)
        if not pain_type or pain_match.status == "unknown":
            continue
        known += 1
        pain_by_type[pain_type.id] = pain_match
        raw = (
            100
            * IMPACT_VALUES[pain_match.impact]
            * STATUS_VALUES[pain_match.status]
            * pain_match.confidence
            / 100
        )
        pain_numerator += raw * pain_type.importance
        pain_denominator += pain_type.importance
        evidence_id = pain_match.evidence_ids[0] if pain_match.evidence_ids else None
        factors.append(
            Factor(
                "pain",
                "pain_type",
                pain_type.id,
                raw,
                raw * pain_type.importance,
                pain_match.status,
                pain_match.confidence,
                pain_match.reasoning_summary,
                evidence_id,
            )
        )
        if evidence_id:
            confidences.append(evidence_confidence[evidence_id] * pain_match.confidence / 100)
    pain = pain_numerator / pain_denominator if pain_denominator else 0.0

    positive_capacity = sum(item.weight for item in buying_types.values()) or 1.0
    negative_capacity = sum(item.weight for item in negative_types.values()) or 1.0
    positive = 0.0
    negative = 0.0
    for buying_match in classification.buying_signals:
        buying_type = buying_types.get(buying_match.signal_type_id)
        if not buying_type:
            continue
        known += 1
        decay = time_decay(buying_match.observed_at, buying_type.decay_days, now)
        raw = 100 * buying_match.confidence / 100 * decay
        positive += raw * buying_type.weight / positive_capacity
        evidence_id = buying_match.evidence_ids[0]
        observed = (
            buying_match.observed_at
            if buying_match.observed_at.tzinfo
            else buying_match.observed_at.replace(tzinfo=UTC)
        )
        age_days = max(0, int((now - observed).total_seconds() / 86400))
        factors.append(
            Factor(
                "intent",
                "buying_signal",
                buying_type.id,
                raw,
                raw * buying_type.weight / positive_capacity,
                buying_match.status,
                buying_match.confidence,
                f"{buying_match.reasoning_summary}; возраст {age_days} дн.; decay={decay:.2f}",
                evidence_id,
            )
        )
        confidences.append(evidence_confidence[evidence_id] * buying_match.confidence / 100)
    hard_negative = False
    for negative_match in classification.negative_signals:
        negative_type = negative_types.get(negative_match.signal_type_id)
        if not negative_type:
            continue
        known += 1
        decay = time_decay(negative_match.observed_at, negative_type.decay_days, now)
        raw = 100 * negative_match.confidence / 100 * decay
        negative += raw * negative_type.weight / negative_capacity
        hard_negative = hard_negative or negative_type.is_hard_exclusion
        evidence_id = negative_match.evidence_ids[0]
        factors.append(
            Factor(
                "intent",
                "negative_signal",
                negative_type.id,
                -raw,
                -raw * negative_type.weight / negative_capacity,
                negative_match.status,
                negative_match.confidence,
                negative_match.reasoning_summary,
                evidence_id,
            )
        )
        confidences.append(evidence_confidence[evidence_id] * negative_match.confidence / 100)
    intent = 0.0 if hard_negative else max(0.0, min(100.0, positive - negative))

    solution_numerator = 0.0
    solution_denominator = 0.0
    missing_required = False
    for solution_rule in solution_rules:
        solution_match = pain_by_type.get(solution_rule.pain_type_id or "")
        if not solution_match:
            missing_required = missing_required or solution_rule.required
            continue
        raw = 100 * IMPACT_VALUES[solution_match.impact] * solution_match.confidence / 100
        solution_numerator += raw * solution_rule.weight
        solution_denominator += solution_rule.weight
        evidence_id = solution_match.evidence_ids[0] if solution_match.evidence_ids else None
        factors.append(
            Factor(
                "solution",
                "solution_fit_rule",
                solution_rule.id,
                raw,
                raw * solution_rule.weight,
                solution_match.status,
                solution_match.confidence,
                solution_rule.explanation or "Услуга связана с подтверждённой болью",
                evidence_id,
            )
        )
    solution_base = solution_numerator / solution_denominator if solution_denominator else 0.0
    solution = (
        0.0 if missing_required else solution_base * 0.9 + (10.0 if has_confirmed_lpr else 0.0)
    )
    values = {"icp": icp, "pain": pain, "intent": intent, "solution": solution}
    completeness = 100 * known / total_configured if total_configured else 0.0
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return Scores(
        round(icp, 2),
        round(pain, 2),
        round(intent, 2),
        round(solution, 2),
        geometric_score(values, weights),
        round(min(100.0, completeness), 2),
        round(confidence, 2),
        factors,
    )


def _valid_classification(
    item: ServiceClassification,
    allowed_evidence: set[str],
    rule_ids: set[str],
    pain_ids: set[str],
    buying_ids: set[str],
    negative_ids: set[str],
) -> bool:
    for valid_icp in item.icp_matches:
        if (
            valid_icp.rule_id not in rule_ids
            or not set(valid_icp.evidence_ids).issubset(allowed_evidence)
            or (valid_icp.status != "unknown" and not valid_icp.evidence_ids)
        ):
            return False
    for valid_pain in item.pains:
        if (
            valid_pain.pain_type_id not in pain_ids
            or not set(valid_pain.evidence_ids).issubset(allowed_evidence)
            or (valid_pain.status != "unknown" and not valid_pain.evidence_ids)
        ):
            return False
    for valid_buying in item.buying_signals:
        if valid_buying.signal_type_id not in buying_ids or not set(
            valid_buying.evidence_ids
        ).issubset(allowed_evidence):
            return False
    for valid_negative in item.negative_signals:
        if valid_negative.signal_type_id not in negative_ids or not set(
            valid_negative.evidence_ids
        ).issubset(allowed_evidence):
            return False
    return True


async def _weights(session: AsyncSession, service_id: str) -> tuple[dict[str, float], str]:
    row = await session.scalar(
        select(ScoreWeightProfile)
        .where(
            ScoreWeightProfile.is_active.is_(True),
            or_(
                ScoreWeightProfile.service_id == service_id,
                ScoreWeightProfile.service_id.is_(None),
            ),
        )
        .order_by(desc(ScoreWeightProfile.service_id))
        .limit(1)
    )
    if not row:
        return DEFAULT_WEIGHTS, SCORE_VERSION
    weights = {
        "icp": row.w_icp,
        "pain": row.w_pain,
        "intent": row.w_intent,
        "solution": row.w_solution,
    }
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-6):
        raise ValueError("Некорректный профиль весов: сумма должна равняться 1")
    return weights, row.version


async def _playbook(
    gateway: GigaChatGateway,
    company: Company,
    service: ServiceCatalog,
    profile: IcpProfile,
    calculation: ScoreCalculation,
    evidence: list[Evidence],
    decision_maker: dict[str, Any],
) -> PlaybookResult:
    request = {
        "company": {"id": company.id, "name": company.name, "inn": company.inn},
        "service": {
            "id": service.id,
            "name": service.name,
            "outcome": profile.product_outcome,
            "discovery_questions": profile.discovery_questions,
            "objections": profile.objections,
        },
        "scores": {
            "sales_opportunity": calculation.sales_opportunity_score,
            "icp": calculation.icp_fit,
            "pain": calculation.pain_score,
            "purchase_probability": calculation.purchase_probability,
            "solution_fit": calculation.solution_fit,
            "data_completeness": calculation.data_completeness,
        },
        "decision_maker": decision_maker,
        "evidence": [
            {"id": item.id, "url": item.source_url, "excerpt": item.excerpt[:600]}
            for item in evidence
        ],
    }
    system = (
        "Подготовь этичный Sales Playbook только по evidence. "
        "Pitch: факт → возможное последствие как гипотеза → вопрос → "
        "релевантность продукта. Не придумывай цифры, намерение купить, бюджет, "
        "людей или обещания. Каждый proof point ссылается на evidence id."
    )
    payload = await gateway.structured_completion(
        system, json.dumps(request, ensure_ascii=False), PlaybookResult.model_json_schema()
    )
    result = PlaybookResult.model_validate(payload)
    allowed = {item.id for item in evidence}
    referenced = set(result.evidence_ids) | {
        eid for proof in result.proof_points for eid in proof.evidence_ids
    }
    if not referenced or not referenced.issubset(allowed):
        raise ValueError("Sales Playbook содержит неизвестные evidence_id")
    return result


async def generate_opportunities(
    session: AsyncSession,
    gateway: GigaChatGateway,
    company: Company,
    score_facts: list[dict[str, Any]],
) -> list[SalesOpportunity]:
    services = list(
        (
            await session.scalars(
                select(ServiceCatalog)
                .where(ServiceCatalog.is_active.is_(True))
                .options(
                    selectinload(ServiceCatalog.icp_profile).selectinload(IcpProfile.rules),
                    selectinload(ServiceCatalog.pain_types),
                    selectinload(ServiceCatalog.buying_signal_types),
                    selectinload(ServiceCatalog.negative_signal_types),
                    selectinload(ServiceCatalog.solution_fit_rules),
                )
            )
        )
        .unique()
        .all()
    )
    services = [item for item in services if item.icp_profile]
    if not services:
        return []
    evidence = list(
        (await session.scalars(select(Evidence).where(Evidence.company_id == company.id))).all()
    )
    allowed_evidence = {item.id for item in evidence}
    evidence_confidence = {item.id: item.confidence for item in evidence}
    request_data = {
        "company": {"id": company.id, "name": company.name, "inn": company.inn},
        "technical_facts": score_facts,
        "evidence": [
            {
                "id": item.id,
                "source_url": item.source_url,
                "observed_at": item.observed_at.isoformat(),
                "excerpt": item.excerpt[:700],
            }
            for item in evidence
        ],
        "services": [
            {
                "id": service.id,
                "name": service.name,
                "description": service.description,
                "icp_rules": [
                    {
                        "id": rule.id,
                        "factor": rule.factor,
                        "operator": rule.operator,
                        "expected": rule.expected_value,
                        "is_exclusion": rule.is_exclusion,
                    }
                    for rule in cast(IcpProfile, service.icp_profile).rules
                ],
                "pain_types": [
                    {
                        "id": item.id,
                        "name": item.name,
                        "funnel_stage": item.funnel_stage,
                        "questions": item.qualification_questions,
                    }
                    for item in service.pain_types
                ],
                "buying_signal_types": [
                    {"id": item.id, "name": item.name} for item in service.buying_signal_types
                ],
                "negative_signal_types": [
                    {"id": item.id, "name": item.name} for item in service.negative_signal_types
                ],
            }
            for service in services
        ],
    }
    system = (
        "Классифицируй только evidence по настроенным правилам. Не выставляй scores "
        "и не создавай факты. Ненайденные CRM, аналитика, реклама и онлайн-запись "
        "имеют status=unknown и дают вопрос, а не боль. Buying signal обязан иметь "
        "источник и дату."
    )
    payload = await gateway.structured_completion(
        system,
        json.dumps(request_data, ensure_ascii=False),
        ClassificationResult.model_json_schema(),
    )
    result = ClassificationResult.model_validate(payload)
    if result.company_id != company.id:
        return []
    session.add(
        PromptVersion(
            purpose="sales_classification",
            version="v1",
            prompt_hash=hashlib.sha256(system.encode()).hexdigest(),
            model=gateway.config["model"],
            input_evidence_ids=sorted(allowed_evidence),
        )
    )
    service_map = {item.id: item for item in services}
    confirmed_person = await session.scalar(
        select(Person)
        .where(Person.company_id == company.id, Person.status == PersonStatus.confirmed)
        .options(selectinload(Person.positions))
        .limit(1)
    )
    decision_maker = (
        {
            "person_id": confirmed_person.id,
            "name": confirmed_person.full_name,
            "role": confirmed_person.positions[0].raw_title if confirmed_person.positions else "",
            "confidence": confirmed_person.confidence,
        }
        if confirmed_person
        else {"person_id": None, "role": "Найти или подтвердить ЛПР", "confidence": 0}
    )
    rows: list[SalesOpportunity] = []
    for classified in result.services:
        service = service_map.get(classified.service_id)
        if not service or not service.icp_profile:
            continue
        pains = {item.id: item for item in service.pain_types}
        buys = {item.id: item for item in service.buying_signal_types}
        negatives = {item.id: item for item in service.negative_signal_types}
        if not _valid_classification(
            classified,
            allowed_evidence,
            {x.id for x in service.icp_profile.rules},
            set(pains),
            set(buys),
            set(negatives),
        ):
            continue
        referenced = (
            {eid for x in classified.icp_matches for eid in x.evidence_ids}
            | {eid for x in classified.pains for eid in x.evidence_ids}
            | {eid for x in classified.buying_signals for eid in x.evidence_ids}
            | {eid for x in classified.negative_signals for eid in x.evidence_ids}
        )
        if not referenced:
            continue
        for classified_pain in classified.pains:
            session.add(
                CompanyPain(
                    company_id=company.id,
                    service_id=service.id,
                    pain_type_id=classified_pain.pain_type_id,
                    evidence_id=(
                        classified_pain.evidence_ids[0] if classified_pain.evidence_ids else None
                    ),
                    status=classified_pain.status,
                    confidence=classified_pain.confidence,
                    impact=classified_pain.impact,
                    explanation=classified_pain.reasoning_summary,
                    qualification_questions=classified_pain.qualification_questions,
                )
            )
        for classified_buying in classified.buying_signals:
            session.add(
                CompanyBuyingSignal(
                    company_id=company.id,
                    service_id=service.id,
                    signal_type_id=classified_buying.signal_type_id,
                    evidence_id=classified_buying.evidence_ids[0],
                    observed_at=classified_buying.observed_at,
                    confidence=classified_buying.confidence,
                    explanation=classified_buying.reasoning_summary,
                )
            )
        for classified_negative in classified.negative_signals:
            session.add(
                CompanyNegativeSignal(
                    company_id=company.id,
                    service_id=service.id,
                    signal_type_id=classified_negative.signal_type_id,
                    evidence_id=classified_negative.evidence_ids[0],
                    observed_at=classified_negative.observed_at,
                    confidence=classified_negative.confidence,
                    explanation=classified_negative.reasoning_summary,
                )
            )
        weights, version = await _weights(session, service.id)
        profile = service.icp_profile
        assert profile is not None
        scores = calculate_scores(
            classified,
            profile.rules,
            pains,
            buys,
            negatives,
            service.solution_fit_rules,
            weights,
            evidence_confidence,
            confirmed_person is not None,
            datetime.now(UTC),
        )
        opportunity = await session.scalar(
            select(SalesOpportunity)
            .where(
                SalesOpportunity.company_id == company.id,
                SalesOpportunity.service_id == service.id,
            )
            .options(selectinload(SalesOpportunity.evidence_links))
        )
        if not opportunity:
            state = (
                DealStatus.ready_to_contact.value
                if scores.total >= service.icp_profile.minimum_sales_score
                and scores.completeness >= 50
                else DealStatus.needs_research.value
            )
            opportunity = SalesOpportunity(
                company_id=company.id,
                service_id=service.id,
                title=service.name,
                score=round(scores.total),
                confidence=round(scores.evidence_confidence),
                priority="high"
                if scores.total >= 75
                else "medium"
                if scores.total >= 50
                else "low",
                summary=classified.summary,
                details={},
                status=state,
            )
            session.add(opportunity)
            await session.flush()
            session.add(
                DealStatusHistory(opportunity_id=opportunity.id, from_status=None, to_status=state)
            )
        calculation = ScoreCalculation(
            company_id=company.id,
            service_id=service.id,
            opportunity_id=opportunity.id,
            icp_fit=scores.icp,
            pain_score=scores.pain,
            purchase_probability=scores.intent,
            solution_fit=scores.solution,
            sales_opportunity_score=scores.total,
            data_completeness=scores.completeness,
            evidence_confidence=scores.evidence_confidence,
            score_version=version,
            weight_snapshot=weights,
            input_snapshot=classified.model_dump(mode="json"),
        )
        calculation.factors = [
            SalesOpportunityFactor(
                dimension=f.dimension,
                rule_type=f.rule_type,
                rule_id=f.rule_id,
                raw_value=f.raw_value,
                weighted_value=f.weighted_value,
                status=f.status,
                confidence=f.confidence,
                explanation=f.explanation,
                evidence_id=f.evidence_id,
            )
            for f in scores.factors
        ]
        session.add(calculation)
        await session.flush()
        opportunity.score = round(scores.total)
        opportunity.confidence = round(scores.evidence_confidence)
        opportunity.summary = classified.summary
        opportunity.evidence_links = [
            OpportunityEvidence(evidence_id=value) for value in sorted(referenced)
        ]
        playbook = await _playbook(
            gateway,
            company,
            service,
            profile,
            calculation,
            [item for item in evidence if item.id in referenced],
            decision_maker,
        )
        playbook_data = playbook.model_dump(mode="json")
        primary_pain = next((x for x in classified.pains if x.status != "unknown"), None)
        why_now = next(iter(classified.buying_signals), None)
        opportunity.details = {
            "scores": {
                "sales_opportunity_score": scores.total,
                "icp_fit": scores.icp,
                "pain": scores.pain,
                "purchase_probability": scores.intent,
                "solution_fit": scores.solution,
                "data_completeness": scores.completeness,
                "evidence_confidence": scores.evidence_confidence,
                "score_version": version,
            },
            "primary_problem": primary_pain.model_dump(mode="json") if primary_pain else None,
            "why_now": why_now.model_dump(mode="json") if why_now else None,
            "decision_maker": decision_maker,
            "sales_playbook": playbook_data,
        }
        session.add(
            SalesPlaybook(
                opportunity_id=opportunity.id,
                calculation_id=calculation.id,
                content=playbook_data,
                evidence_ids=playbook.evidence_ids,
            )
        )
        rows.append(opportunity)
    return rows
