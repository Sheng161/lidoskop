import csv
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.connectors import DaDataConnector, YandexSearchConnector
from app.db import get_session
from app.gigachat import GigaChatGateway
from app.models import (
    Address,
    AppSetting,
    AuditEvent,
    BuyingSignalType,
    Company,
    CompanyBuyingSignal,
    DealStatusHistory,
    Evidence,
    IcpProfile,
    IcpRule,
    JobStatus,
    ManagerNote,
    NegativeSignalType,
    NextAction,
    OpportunityFeedback,
    PainType,
    Person,
    PersonStatus,
    Position,
    SalesOpportunity,
    ScoreCalculation,
    ScoreWeightProfile,
    SearchJob,
    ServiceCatalog,
    ServiceSignal,
    SolutionFitRule,
    SourceConnector,
)
from app.schemas import (
    ConnectorInput,
    DealUpdateInput,
    FeedbackInput,
    GigaChatInput,
    JobResponse,
    SalesProfileInput,
    SearchRequest,
    ServiceInput,
)
from app.security import SecretStoreError, mask_secret
from app.serialization import company_detail
from app.settings_store import (
    get_connector_config,
    get_gigachat_config,
    save_connector_config,
    save_gigachat_config,
)
from app.worker import plan_search_task, run_research_task

router = APIRouter(prefix="/api/v1")
CONNECTOR_NAMES = {"dadata": "DaData (организации)", "yandex_search": "Yandex Search API"}


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.scalar(select(func.now()))
    return {"status": "ok", "database": "connected"}


@router.get("/diagnostics")
async def diagnostics(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    connectors = list((await session.scalars(select(SourceConnector))).all())
    giga = await session.get(AppSetting, "gigachat")
    recent = list(
        (
            await session.scalars(
                select(AuditEvent).order_by(desc(AuditEvent.occurred_at)).limit(30)
            )
        ).all()
    )
    return {
        "gigachat": "configured" if giga and giga.encrypted_value else "not_connected",
        "connectors": [
            {"kind": row.kind, "status": row.status, "last_error": row.last_error}
            for row in connectors
        ],
        "audit": [
            {
                "occurred_at": row.occurred_at,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "metadata": row.safe_metadata,
            }
            for row in recent
        ],
    }


@router.get("/settings/gigachat")
async def get_gigachat(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    stored = await get_gigachat_config(session)
    if not stored:
        return {"status": "not_connected", "authorization_key_masked": None}
    config, key = stored
    return {**config, "status": "configured", "authorization_key_masked": mask_secret(key)}


@router.put("/settings/gigachat")
async def put_gigachat(
    payload: GigaChatInput, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    public = payload.model_dump(mode="json", exclude={"authorization_key"})
    try:
        await save_gigachat_config(session, public, payload.authorization_key)
        session.add(AuditEvent(action="gigachat_settings_updated"))
        await session.commit()
    except (ValueError, SecretStoreError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "configured"}


@router.post("/settings/gigachat/test")
async def test_gigachat(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    try:
        stored = await get_gigachat_config(session)
        if not stored:
            raise HTTPException(status_code=409, detail="GigaChat не подключён")
        config, key = stored
        message = await GigaChatGateway(config, key).test_connection()
        return {"status": "connected", "message": message}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/connectors")
async def list_connectors(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = {row.kind: row for row in (await session.scalars(select(SourceConnector))).all()}
    return [
        {
            "kind": kind,
            "display_name": display_name,
            "is_enabled": rows[kind].is_enabled if kind in rows else False,
            "status": rows[kind].status if kind in rows else "not_connected",
            "last_error": rows[kind].last_error if kind in rows else None,
            "rate_limit_per_minute": rows[kind].rate_limit_per_minute if kind in rows else 30,
            "configured": bool(rows[kind].encrypted_config) if kind in rows else False,
        }
        for kind, display_name in CONNECTOR_NAMES.items()
    ]


@router.put("/connectors/{kind}")
async def put_connector(
    kind: str, payload: ConnectorInput, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    if kind not in CONNECTOR_NAMES:
        raise HTTPException(status_code=404, detail="Неизвестный коннектор")
    required = {"dadata": {"token"}, "yandex_search": {"api_key", "folder_id"}}[kind]
    existing = await get_connector_config(session, kind)
    if payload.is_enabled and not required.issubset(payload.config) and not existing:
        raise HTTPException(status_code=422, detail=f"Нужны поля: {', '.join(sorted(required))}")
    try:
        await save_connector_config(
            session,
            kind,
            CONNECTOR_NAMES[kind],
            payload.is_enabled,
            payload.rate_limit_per_minute,
            payload.config,
        )
        session.add(AuditEvent(action="connector_settings_updated", entity_type="connector"))
        await session.commit()
    except SecretStoreError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "configured"}


@router.post("/connectors/{kind}/test")
async def test_connector(kind: str, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    stored = await get_connector_config(session, kind)
    if not stored or not stored[0].is_enabled:
        raise HTTPException(status_code=409, detail="Источник не подключён")
    row, config = stored
    try:
        if kind == "dadata":
            message = await DaDataConnector(config["token"]).test_connection()
        elif kind == "yandex_search":
            message = await YandexSearchConnector(
                config["api_key"], config["folder_id"]
            ).test_connection()
        else:
            raise HTTPException(status_code=404, detail="Неизвестный коннектор")
        row.status = "connected"
        row.last_error = None
        await session.commit()
        return {"status": "connected", "message": message}
    except HTTPException:
        raise
    except Exception as exc:
        row.status = "error"
        row.last_error = str(exc)[:500]
        await session.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def serialize_service(row: ServiceCatalog) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "category": row.category,
        "target_industries": row.target_industries,
        "exclusions": row.exclusions,
        "min_company_size": row.min_company_size,
        "max_company_size": row.max_company_size,
        "geography": row.geography,
        "required_evidence": row.required_evidence,
        "target_roles": row.target_roles,
        "business_value": row.business_value,
        "price_range": row.price_range,
        "priority": row.priority,
        "is_active": row.is_active,
        "signals": [{"kind": signal.kind, "text": signal.text} for signal in row.signals],
        "has_sales_profile": row.icp_profile is not None,
    }


@router.get("/services")
async def list_services(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = list(
        (
            await session.scalars(
                select(ServiceCatalog)
                .options(
                    selectinload(ServiceCatalog.signals),
                    selectinload(ServiceCatalog.icp_profile),
                )
                .order_by(desc(ServiceCatalog.priority))
            )
        ).all()
    )
    return [serialize_service(row) for row in rows]


@router.post("/services", status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: ServiceInput, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    data = payload.model_dump(exclude={"signals"})
    row = ServiceCatalog(**data)
    row.signals = [ServiceSignal(**signal.model_dump()) for signal in payload.signals]
    session.add(row)
    await session.commit()
    refreshed = await session.scalar(
        select(ServiceCatalog)
        .where(ServiceCatalog.id == row.id)
        .options(
            selectinload(ServiceCatalog.signals),
            selectinload(ServiceCatalog.icp_profile),
        )
    )
    assert refreshed is not None
    return serialize_service(refreshed)


def _serialize_sales_profile(service: ServiceCatalog) -> dict[str, Any] | None:
    profile = service.icp_profile
    if not profile:
        return None
    return {
        "id": profile.id,
        "business_models": profile.business_models,
        "product_outcome": profile.product_outcome,
        "solved_funnel_stages": profile.solved_funnel_stages,
        "required_traits": profile.required_traits,
        "desired_traits": profile.desired_traits,
        "contraindications": profile.contraindications,
        "decision_maker_rules": profile.decision_maker_rules,
        "discovery_questions": profile.discovery_questions,
        "objections": profile.objections,
        "materials": profile.materials,
        "reference_rules": profile.reference_rules,
        "minimum_sales_score": profile.minimum_sales_score,
        "icp_rules": [
            {
                "id": rule.id,
                "factor": rule.factor,
                "operator": rule.operator,
                "expected_value": rule.expected_value,
                "weight": rule.weight,
                "is_exclusion": rule.is_exclusion,
                "evidence_required": rule.evidence_required,
            }
            for rule in profile.rules
        ],
        "pain_types": [
            {
                "id": item.id,
                "name": item.name,
                "normalized_type": item.normalized_type,
                "funnel_stage": item.funnel_stage,
                "importance": item.importance,
                "qualification_questions": item.qualification_questions,
            }
            for item in service.pain_types
        ],
        "buying_signals": [
            {
                "id": item.id,
                "name": item.name,
                "normalized_type": item.normalized_type,
                "weight": item.weight,
                "decay_days": item.decay_days,
            }
            for item in service.buying_signal_types
        ],
        "negative_signals": [
            {
                "id": item.id,
                "name": item.name,
                "normalized_type": item.normalized_type,
                "weight": item.weight,
                "decay_days": item.decay_days,
                "is_hard_exclusion": item.is_hard_exclusion,
            }
            for item in service.negative_signal_types
        ],
        "solution_fit_rules": [
            {
                "id": item.id,
                "pain_type_id": item.pain_type_id,
                "funnel_stage": item.funnel_stage,
                "weight": item.weight,
                "required": item.required,
                "explanation": item.explanation,
            }
            for item in service.solution_fit_rules
        ],
    }


def _sales_profile_options() -> tuple[Any, ...]:
    return (
        selectinload(ServiceCatalog.icp_profile).selectinload(IcpProfile.rules),
        selectinload(ServiceCatalog.pain_types),
        selectinload(ServiceCatalog.buying_signal_types),
        selectinload(ServiceCatalog.negative_signal_types),
        selectinload(ServiceCatalog.solution_fit_rules),
    )


@router.get("/services/{service_id}/sales-profile")
async def get_sales_profile(
    service_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    service = await session.scalar(
        select(ServiceCatalog)
        .where(ServiceCatalog.id == service_id)
        .options(*_sales_profile_options())
    )
    if not service:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    profile = _serialize_sales_profile(service)
    if not profile:
        raise HTTPException(status_code=404, detail="Sales-профиль услуги не настроен")
    return profile


@router.put("/services/{service_id}/sales-profile")
async def put_sales_profile(
    service_id: str,
    payload: SalesProfileInput,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = await session.scalar(
        select(ServiceCatalog)
        .where(ServiceCatalog.id == service_id)
        .options(*_sales_profile_options())
    )
    if not service:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    if service.icp_profile:
        await session.delete(service.icp_profile)
    for collection in (
        service.pain_types,
        service.buying_signal_types,
        service.negative_signal_types,
        service.solution_fit_rules,
    ):
        for item in list(collection):
            await session.delete(item)
    await session.flush()
    profile_data = payload.model_dump(
        exclude={
            "icp_rules",
            "pain_types",
            "buying_signals",
            "negative_signals",
            "solution_fit_rules",
            "weights",
        }
    )
    profile = IcpProfile(service_id=service.id, **profile_data)
    profile.rules = [IcpRule(**item.model_dump()) for item in payload.icp_rules]
    session.add(profile)
    pains = [PainType(service_id=service.id, **item.model_dump()) for item in payload.pain_types]
    buys = [
        BuyingSignalType(
            service_id=service.id,
            **item.model_dump(exclude={"is_hard_exclusion"}),
        )
        for item in payload.buying_signals
    ]
    negatives = [
        NegativeSignalType(service_id=service.id, **item.model_dump())
        for item in payload.negative_signals
    ]
    session.add_all([*pains, *buys, *negatives])
    await session.flush()
    for fit_input in payload.solution_fit_rules:
        pain_id = None
        if fit_input.pain_type_index is not None:
            if fit_input.pain_type_index >= len(pains):
                raise HTTPException(status_code=422, detail="Неверный pain_type_index")
            pain_id = pains[fit_input.pain_type_index].id
        session.add(
            SolutionFitRule(
                service_id=service.id,
                pain_type_id=pain_id,
                **fit_input.model_dump(exclude={"pain_type_index"}),
            )
        )
    old_weights = list(
        (
            await session.scalars(
                select(ScoreWeightProfile).where(
                    ScoreWeightProfile.service_id == service.id,
                    ScoreWeightProfile.is_active.is_(True),
                )
            )
        ).all()
    )
    for old_weight in old_weights:
        old_weight.is_active = False
    session.add(
        ScoreWeightProfile(
            service_id=service.id,
            name=f"{service.name} v{len(old_weights) + 1}",
            version=f"sales-v{len(old_weights) + 1}",
            **payload.weights.model_dump(),
        )
    )
    session.add(
        AuditEvent(action="sales_profile_updated", entity_type="service", entity_id=service.id)
    )
    await session.commit()
    refreshed = await session.scalar(
        select(ServiceCatalog)
        .where(ServiceCatalog.id == service.id)
        .options(*_sales_profile_options())
    )
    assert refreshed is not None
    return _serialize_sales_profile(refreshed) or {}


@router.put("/services/{service_id}")
async def update_service(
    service_id: str, payload: ServiceInput, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    row = await session.scalar(
        select(ServiceCatalog)
        .where(ServiceCatalog.id == service_id)
        .options(selectinload(ServiceCatalog.signals))
    )
    if not row:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    for key, value in payload.model_dump(exclude={"signals"}).items():
        setattr(row, key, value)
    row.signals = [ServiceSignal(**signal.model_dump()) for signal in payload.signals]
    await session.commit()
    refreshed = await session.scalar(
        select(ServiceCatalog)
        .where(ServiceCatalog.id == row.id)
        .options(
            selectinload(ServiceCatalog.signals),
            selectinload(ServiceCatalog.icp_profile),
        )
    )
    assert refreshed is not None
    return serialize_service(refreshed)


@router.delete("/services/{service_id}", status_code=204)
async def delete_service(service_id: str, session: AsyncSession = Depends(get_session)) -> Response:
    row = await session.get(ServiceCatalog, service_id)
    if not row:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    await session.delete(row)
    await session.commit()
    return Response(status_code=204)


@router.post("/search/plan", status_code=status.HTTP_202_ACCEPTED)
async def create_search_plan(
    payload: SearchRequest, session: AsyncSession = Depends(get_session)
) -> JobResponse:
    if not await get_gigachat_config(session):
        raise HTTPException(status_code=409, detail="Сначала подключите GigaChat")
    digest = hashlib.sha256(
        (payload.model_dump_json() + datetime.now(UTC).isoformat()).encode()
    ).hexdigest()
    row = SearchJob(
        **payload.model_dump(),
        status=JobStatus.queued,
        stage="planning_queued",
        idempotency_key=digest,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    plan_search_task.delay(row.id)
    return JobResponse.model_validate(row)


@router.get("/jobs")
async def list_jobs(session: AsyncSession = Depends(get_session)) -> list[JobResponse]:
    rows = list(
        (await session.scalars(select(SearchJob).order_by(desc(SearchJob.created_at)))).all()
    )
    return [JobResponse.model_validate(row) for row in rows]


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    row = await session.scalar(
        select(SearchJob).where(SearchJob.id == job_id).options(selectinload(SearchJob.plan))
    )
    if not row:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return {
        **JobResponse.model_validate(row).model_dump(),
        "plan": row.plan.structured_plan if row.plan else None,
    }


@router.post("/jobs/{job_id}/start", status_code=202)
async def start_job(job_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    row = await session.scalar(
        select(SearchJob).where(SearchJob.id == job_id).options(selectinload(SearchJob.plan))
    )
    if not row:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if not row.plan:
        raise HTTPException(status_code=409, detail="План ещё не готов")
    if row.status not in {JobStatus.draft, JobStatus.failed, JobStatus.partial}:
        raise HTTPException(status_code=409, detail="Задачу нельзя запустить в текущем состоянии")
    row.status = JobStatus.queued
    row.stage = "research_queued"
    row.cancel_requested = False
    await session.commit()
    run_research_task.delay(row.id)
    return {"status": "queued"}


@router.post("/jobs/{job_id}/cancel", status_code=202)
async def cancel_job(job_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    row = await session.get(SearchJob, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    row.cancel_requested = True
    await session.commit()
    return {"status": "cancellation_requested"}


@router.get("/companies")
async def list_companies(
    q: str | None = None,
    city: str | None = None,
    job_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    stmt = select(Company).options(selectinload(Company.addresses), selectinload(Company.scores))
    if q:
        stmt = stmt.where(or_(Company.name.ilike(f"%{q}%"), Company.inn.ilike(f"%{q}%")))
    if job_id:
        stmt = stmt.where(Company.job_id == job_id)
    if city:
        stmt = stmt.where(Company.addresses.any(city=city))
    rows = list((await session.scalars(stmt.order_by(desc(Company.created_at)))).unique().all())
    return [
        {
            "id": row.id,
            "name": row.name,
            "inn": row.inn,
            "ogrn": row.ogrn,
            "status": row.status,
            "website": row.website,
            "city": row.addresses[0].city if row.addresses else None,
            "score": row.scores[-1].total if row.scores else None,
        }
        for row in rows
    ]


@router.get("/companies/{company_id}")
async def get_company(
    company_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    detail = await company_detail(session, company_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    return detail


@router.delete("/companies/{company_id}", status_code=204)
async def delete_company(company_id: str, session: AsyncSession = Depends(get_session)) -> Response:
    row = await session.get(Company, company_id)
    if not row:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    await session.delete(row)
    session.add(AuditEvent(action="company_deleted", entity_type="company", entity_id=company_id))
    await session.commit()
    return Response(status_code=204)


@router.get("/people")
async def list_people(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = list(
        (
            await session.scalars(
                select(Person)
                .options(selectinload(Person.positions), selectinload(Person.contacts))
                .order_by(desc(Person.created_at))
            )
        ).all()
    )
    return [
        {
            "id": row.id,
            "company_id": row.company_id,
            "full_name": row.full_name,
            "status": row.status.value,
            "confidence": row.confidence,
            "positions": [position.raw_title for position in row.positions],
            "contacts": [
                {
                    "kind": item.kind,
                    "value": item.value,
                    "origin": item.origin,
                    "technical_status": item.technical_status,
                }
                for item in row.contacts
            ],
        }
        for row in rows
    ]


@router.delete("/people/{person_id}", status_code=204)
async def delete_person(person_id: str, session: AsyncSession = Depends(get_session)) -> Response:
    row = await session.get(Person, person_id)
    if not row:
        raise HTTPException(status_code=404, detail="ЛПР не найден")
    await session.delete(row)
    session.add(AuditEvent(action="person_deleted", entity_type="person", entity_id=person_id))
    await session.commit()
    return Response(status_code=204)


def _latest_calculation(row: SalesOpportunity) -> ScoreCalculation | None:
    return max(row.calculations, key=lambda item: item.calculated_at) if row.calculations else None


def _serialize_opportunity(row: SalesOpportunity) -> dict[str, Any]:
    calculation = _latest_calculation(row)
    scores = (
        {
            "sales_opportunity_score": calculation.sales_opportunity_score,
            "icp_fit": calculation.icp_fit,
            "pain": calculation.pain_score,
            "purchase_probability": calculation.purchase_probability,
            "solution_fit": calculation.solution_fit,
            "data_completeness": calculation.data_completeness,
            "evidence_confidence": calculation.evidence_confidence,
            "score_version": calculation.score_version,
            "calculated_at": calculation.calculated_at,
        }
        if calculation
        else None
    )
    return {
        "id": row.id,
        "company_id": row.company_id,
        "service_id": row.service_id,
        "title": row.title,
        "score": row.score,
        "confidence": row.confidence,
        "priority": row.priority,
        "status": row.status,
        "summary": row.summary,
        "details": row.details,
        "scores": scores,
    }


@router.get("/opportunities")
async def list_opportunities(
    min_score: float = 0,
    min_icp: float = 0,
    min_pain: float = 0,
    min_purchase_probability: float = 0,
    min_solution_fit: float = 0,
    min_completeness: float = 0,
    service_id: str | None = None,
    deal_status: str | None = None,
    city: str | None = None,
    region: str | None = None,
    lpr_role: str | None = None,
    has_confirmed_lpr: bool | None = None,
    signal_max_age_days: int | None = Query(default=None, ge=1, le=3650),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    stmt = select(SalesOpportunity).options(selectinload(SalesOpportunity.calculations))
    if service_id:
        stmt = stmt.where(SalesOpportunity.service_id == service_id)
    if deal_status:
        stmt = stmt.where(SalesOpportunity.status == deal_status)
    if city:
        stmt = stmt.where(
            SalesOpportunity.company_id.in_(
                select(Address.company_id).where(Address.city.ilike(f"%{city}%"))
            )
        )
    if region:
        stmt = stmt.where(
            SalesOpportunity.company_id.in_(
                select(Address.company_id).where(Address.region.ilike(f"%{region}%"))
            )
        )
    confirmed_people = select(Person.company_id).where(Person.status == PersonStatus.confirmed)
    if lpr_role:
        confirmed_people = confirmed_people.join(Position, Position.person_id == Person.id).where(
            Position.raw_title.ilike(f"%{lpr_role}%")
        )
    if has_confirmed_lpr is True or lpr_role:
        stmt = stmt.where(SalesOpportunity.company_id.in_(confirmed_people))
    elif has_confirmed_lpr is False:
        stmt = stmt.where(SalesOpportunity.company_id.not_in(confirmed_people))
    if signal_max_age_days:
        threshold = datetime.now(UTC) - timedelta(days=signal_max_age_days)
        stmt = stmt.where(
            SalesOpportunity.company_id.in_(
                select(CompanyBuyingSignal.company_id).where(
                    CompanyBuyingSignal.observed_at >= threshold,
                    CompanyBuyingSignal.service_id == SalesOpportunity.service_id,
                )
            )
        )
    rows = list((await session.scalars(stmt.order_by(desc(SalesOpportunity.score)))).unique().all())
    result = []
    for row in rows:
        calc = _latest_calculation(row)
        if not calc:
            continue
        if (
            calc.sales_opportunity_score < min_score
            or calc.icp_fit < min_icp
            or calc.pain_score < min_pain
            or calc.purchase_probability < min_purchase_probability
            or calc.solution_fit < min_solution_fit
            or calc.data_completeness < min_completeness
        ):
            continue
        result.append(_serialize_opportunity(row))
    return result


@router.get("/opportunities/{opportunity_id}")
async def get_opportunity(
    opportunity_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    row = await session.scalar(
        select(SalesOpportunity)
        .where(SalesOpportunity.id == opportunity_id)
        .options(
            selectinload(SalesOpportunity.calculations).selectinload(ScoreCalculation.factors),
            selectinload(SalesOpportunity.playbooks),
            selectinload(SalesOpportunity.status_history),
            selectinload(SalesOpportunity.manager_notes),
            selectinload(SalesOpportunity.next_actions),
            selectinload(SalesOpportunity.evidence_links),
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Возможность не найдена")
    result = _serialize_opportunity(row)
    calculation = _latest_calculation(row)
    result.update(
        {
            "factors": [
                {
                    "dimension": item.dimension,
                    "rule_type": item.rule_type,
                    "raw_value": item.raw_value,
                    "weighted_value": item.weighted_value,
                    "status": item.status,
                    "confidence": item.confidence,
                    "explanation": item.explanation,
                    "evidence_id": item.evidence_id,
                }
                for item in (calculation.factors if calculation else [])
            ],
            "calculation_history": [
                {
                    "id": item.id,
                    "calculated_at": item.calculated_at,
                    "score": item.sales_opportunity_score,
                    "version": item.score_version,
                }
                for item in sorted(row.calculations, key=lambda value: value.calculated_at)
            ],
            "playbook": row.playbooks[-1].content if row.playbooks else None,
            "status_history": [
                {
                    "from": item.from_status,
                    "to": item.to_status,
                    "reason": item.reason,
                    "changed_at": item.changed_at,
                }
                for item in row.status_history
            ],
            "notes": [
                {"note": item.note, "created_at": item.created_at} for item in row.manager_notes
            ],
            "next_actions": [
                {
                    "id": item.id,
                    "action": item.action,
                    "due_at": item.due_at,
                    "status": item.status,
                }
                for item in row.next_actions
            ],
            "evidence_ids": [item.evidence_id for item in row.evidence_links],
        }
    )
    return result


@router.put("/opportunities/{opportunity_id}/deal")
async def update_deal(
    opportunity_id: str,
    payload: DealUpdateInput,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    row = await session.get(SalesOpportunity, opportunity_id)
    if not row:
        raise HTTPException(status_code=404, detail="Возможность не найдена")
    previous = row.status
    row.status = payload.status
    session.add(
        DealStatusHistory(
            opportunity_id=row.id,
            from_status=previous,
            to_status=payload.status,
            reason=payload.reason,
        )
    )
    if payload.note:
        session.add(ManagerNote(opportunity_id=row.id, note=payload.note))
    if payload.next_action:
        session.add(
            NextAction(
                opportunity_id=row.id,
                action=payload.next_action,
                due_at=payload.next_action_at,
            )
        )
    await session.commit()
    return {"status": row.status}


@router.post("/opportunities/{opportunity_id}/feedback")
async def opportunity_feedback(
    opportunity_id: str, payload: FeedbackInput, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    row = await session.get(SalesOpportunity, opportunity_id)
    if not row:
        raise HTTPException(status_code=404, detail="Возможность не найдена")
    if payload.decision == "accepted":
        row.status = "ready_to_contact"
    elif payload.decision == "rejected":
        row.status = "not_a_fit"
    session.add(OpportunityFeedback(opportunity_id=row.id, **payload.model_dump()))
    await session.commit()
    return {"status": row.status}


@router.get("/evidence/{evidence_id}")
async def get_evidence(
    evidence_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    row = await session.get(Evidence, evidence_id)
    if not row:
        raise HTTPException(status_code=404, detail="Доказательство не найдено")
    return {
        "id": row.id,
        "source_type": row.source_type,
        "source_url": row.source_url,
        "page_title": row.page_title,
        "excerpt": row.excerpt,
        "extraction_method": row.extraction_method,
        "content_hash": row.content_hash,
        "observed_at": row.observed_at,
        "confidence": row.confidence,
    }


@router.get("/graph/{company_id}")
async def company_graph(
    company_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    detail = await company_detail(session, company_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    nodes = [{"id": company_id, "type": "company", "label": detail["name"]}]
    edges = []
    for resource in detail["resources"]:
        nodes.append(
            {
                "id": resource["id"],
                "type": resource["kind"],
                "label": resource["title"] or resource["url"],
            }
        )
        edges.append({"source": company_id, "target": resource["id"], "relation": "owns"})
    for person in detail["people"]:
        nodes.append({"id": person["id"], "type": "person", "label": person["full_name"]})
        edges.append({"source": person["id"], "target": company_id, "relation": "works_at"})
    return {"nodes": nodes, "edges": edges}


async def _export_rows(session: AsyncSession, job_id: str | None) -> list[dict[str, Any]]:
    stmt = select(Company).options(selectinload(Company.addresses), selectinload(Company.scores))
    if job_id:
        stmt = stmt.where(Company.job_id == job_id)
    companies = list((await session.scalars(stmt)).unique().all())
    return [
        {
            "name": row.name,
            "inn": row.inn or "",
            "ogrn": row.ogrn or "",
            "legal_address": row.addresses[0].full_address if row.addresses else "",
            "city": row.addresses[0].city if row.addresses else "",
            "website": row.website or "",
            "score": row.scores[-1].total if row.scores else "",
        }
        for row in companies
    ]


@router.get("/exports/{export_format}")
async def export_companies(
    export_format: Literal["csv", "json", "xlsx"],
    job_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    rows = await _export_rows(session, job_id)
    filename = f"lidoskop-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.{export_format}"
    if export_format == "json":
        data = json.dumps(rows, ensure_ascii=False, indent=2).encode()
        media = "application/json"
    elif export_format == "csv":
        text = io.StringIO()
        writer = csv.DictWriter(
            text,
            fieldnames=list(rows[0])
            if rows
            else ["name", "inn", "ogrn", "legal_address", "city", "website", "score"],
        )
        writer.writeheader()
        writer.writerows(rows)
        data = ("\ufeff" + text.getvalue()).encode("utf-8")
        media = "text/csv; charset=utf-8"
    else:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Компании"
        headers = (
            list(rows[0])
            if rows
            else ["name", "inn", "ogrn", "legal_address", "city", "website", "score"]
        )
        sheet.append(headers)
        for row in rows:
            sheet.append([row[key] for key in headers])
        binary = io.BytesIO()
        workbook.save(binary)
        data = binary.getvalue()
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
