import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.connectors import (
    CompanyRecord,
    DaDataConnector,
    YandexSearchConnector,
    safe_evidence_excerpt,
)
from app.contacts import check_email_mx
from app.crawler import SafeCrawler
from app.gigachat import GigaChatGateway
from app.models import (
    Address,
    AuditEvent,
    Company,
    CompanyName,
    Contact,
    CrawlPage,
    DigitalPresenceScore,
    Evidence,
    JobStatus,
    Person,
    PersonStatus,
    Position,
    Resource,
    ScoreFactor,
    SearchJob,
    SearchPlan,
)
from app.opportunities import generate_opportunities
from app.schemas import SearchPlanData, SearchRequest
from app.scoring import calculate_score
from app.settings_store import get_connector_config, get_gigachat_config

BLOCKED_SITE_DOMAINS = {
    "dadata.ru",
    "rusprofile.ru",
    "checko.ru",
    "list-org.com",
    "sbis.ru",
    "spark-interfax.ru",
    "audit-it.ru",
    "zachestnyibiznes.ru",
    "vk.com",
}


def normalize_name(value: str) -> str:
    return re.sub(r"[^а-яa-z0-9]+", " ", value.lower()).strip()


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def _gigachat(session: AsyncSession) -> GigaChatGateway:
    stored = await get_gigachat_config(session)
    if not stored:
        raise RuntimeError("GigaChat не подключён")
    config, key = stored
    return GigaChatGateway(config, key)


async def plan_search(session: AsyncSession, job_id: str) -> None:
    job = await session.get(SearchJob, job_id)
    if not job:
        return
    try:
        job.status = JobStatus.running
        job.stage = "planning"
        job.progress = 10
        await session.commit()
        gateway = await _gigachat(session)
        request = SearchRequest(
            query=job.query,
            city=job.city,
            region=job.region,
            federal_district=job.federal_district,
            target_roles=job.target_roles,
        )
        plan = await gateway.build_search_plan(request)
        session.add(
            SearchPlan(
                job_id=job.id,
                structured_plan=plan.model_dump(),
                prompt_version="search-plan-v1",
                model=gateway.config["model"],
            )
        )
        job.status = JobStatus.draft
        job.stage = "plan_ready"
        job.progress = 20
        session.add(
            AuditEvent(action="search_plan_created", entity_type="search_job", entity_id=job.id)
        )
        await session.commit()
    except Exception as exc:
        job.status = JobStatus.failed
        job.stage = "planning_failed"
        job.error = str(exc)[:1000]
        await session.commit()


async def _check_cancel(session: AsyncSession, job: SearchJob) -> bool:
    await session.refresh(job, ["cancel_requested"])
    if job.cancel_requested:
        job.status = JobStatus.cancelled
        job.stage = "cancelled"
        await session.commit()
        return True
    return False


def _candidate_site(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return bool(
        host
        and not any(host == value or host.endswith("." + value) for value in BLOCKED_SITE_DOMAINS)
    )


async def _discover_site(search: YandexSearchConnector | None, company: Company) -> str | None:
    if not search:
        return None
    query = f'"{company.name}" {company.inn or ""} официальный сайт'
    for url in await search.search(query, 8):
        if _candidate_site(url):
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}/"
    return None


async def _save_company_from_record(
    session: AsyncSession, job: SearchJob, record: CompanyRecord
) -> tuple[Company, Evidence]:
    inn = record.inn
    company = await session.scalar(select(Company).where(Company.inn == inn)) if inn else None
    if company:
        return company, await session.scalar(
            select(Evidence).where(Evidence.company_id == company.id).limit(1)
        )  # type: ignore[return-value]
    excerpt = safe_evidence_excerpt(record)
    evidence = Evidence(
        source_type="dadata_party",
        source_url=DaDataConnector.endpoint,
        page_title="DaData: подсказки по организациям",
        excerpt=excerpt,
        extraction_method="api_json",
        content_hash=hash_text(excerpt),
        confidence=95,
    )
    company = Company(
        name=record.name,
        normalized_name=normalize_name(record.name),
        inn=inn,
        ogrn=record.ogrn,
        legal_form=record.legal_form,
        status=record.status,
        job_id=job.id,
    )
    session.add_all([company, evidence])
    await session.flush()
    evidence.company_id = company.id
    company.names.append(CompanyName(value=company.name, kind="official", evidence_id=evidence.id))
    if record.address:
        company.addresses.append(
            Address(
                kind="legal",
                full_address=record.address,
                federal_district=record.federal_district,
                region=record.region,
                city=record.city,
                evidence_id=evidence.id,
            )
        )
    if record.manager_name and record.manager_post:
        person = Person(
            full_name=record.manager_name,
            confidence=92,
            confidence_reason=(
                "Руководитель указан в данных организации, полученных через DaData из ЕГРЮЛ"
            ),
            status=PersonStatus.confirmed,
            last_verified_at=datetime.now(UTC),
        )
        person.positions.append(
            Position(
                normalized_title="генеральный директор",
                raw_title=record.manager_post,
                evidence_id=evidence.id,
            )
        )
        company.people.append(person)
    return company, evidence


async def _crawl_and_score(
    session: AsyncSession, company: Company, website: str
) -> tuple[list[dict[str, object]], bool]:
    result = await SafeCrawler().crawl(website)
    combined = " ".join(page.text.lower() for page in result.pages)
    name_words = [word for word in normalize_name(company.name).split() if len(word) > 4]
    identity_matches = sum(word in combined for word in name_words)
    verified = bool(
        result.pages
        and (
            (company.inn and company.inn in combined)
            or (name_words and identity_matches >= min(2, len(name_words)))
        )
    )
    if not verified:
        return [], False
    evidence_by_url: dict[str, Evidence] = {}
    for page in result.pages:
        excerpt = page.text[:1000]
        evidence = Evidence(
            company_id=company.id,
            source_type="official_site",
            source_url=page.url,
            page_title=page.title,
            excerpt=excerpt,
            extraction_method="robots_aware_html",
            content_hash=page.content_hash,
            confidence=90,
        )
        session.add(evidence)
        await session.flush()
        evidence_by_url[page.url] = evidence
        company.resources.append(
            Resource(
                kind="website_page",
                url=page.url,
                title=page.title,
                evidence_id=evidence.id,
                confidence=90,
            )
        )
        session.add(
            CrawlPage(
                company_id=company.id,
                url=page.url,
                status_code=page.status_code,
                content_hash=page.content_hash,
                robots_allowed=True,
            )
        )
        for email in page.emails:
            technical_status = await check_email_mx(email)
            session.add(
                Contact(
                    company_id=company.id,
                    kind="email",
                    value=email,
                    origin="official_site",
                    is_confirmed=True,
                    technical_status=technical_status,
                    evidence_id=evidence.id,
                )
            )
        for phone in page.phones:
            session.add(
                Contact(
                    company_id=company.id,
                    kind="phone",
                    value=phone,
                    origin="official_site",
                    is_confirmed=True,
                    evidence_id=evidence.id,
                )
            )
    for blocked_url in result.blocked_urls:
        session.add(CrawlPage(company_id=company.id, url=blocked_url[:2048], robots_allowed=False))
    factors = calculate_score(result, company.name, company.inn)
    score = DigitalPresenceScore(total=sum(item.points for item in factors), version="v1")
    facts: list[dict[str, object]] = []
    for item in factors:
        factor_evidence = evidence_by_url.get(item.evidence_url or "")
        score.factors.append(
            ScoreFactor(
                category=item.category,
                weight=item.weight,
                points=item.points,
                explanation=item.explanation,
                evidence_id=factor_evidence.id if factor_evidence else None,
            )
        )
        facts.append(
            {
                "category": item.category,
                "weight": item.weight,
                "points": item.points,
                "explanation": item.explanation,
                "evidence_id": factor_evidence.id if factor_evidence else None,
            }
        )
    company.scores.append(score)
    return facts, True


async def run_research(session: AsyncSession, job_id: str) -> None:
    job = await session.scalar(
        select(SearchJob).where(SearchJob.id == job_id).options(selectinload(SearchJob.plan))
    )
    if not job or not job.plan:
        return
    try:
        job.status = JobStatus.running
        job.stage = "companies"
        job.progress = 25
        job.error = None
        await session.commit()
        dadata_stored = await get_connector_config(session, "dadata")
        if not dadata_stored or not dadata_stored[0].is_enabled:
            raise RuntimeError("Источник организаций DaData не подключён")
        dadata = DaDataConnector(dadata_stored[1]["token"])
        yandex_stored = await get_connector_config(session, "yandex_search")
        yandex = None
        if yandex_stored and yandex_stored[0].is_enabled:
            yandex = YandexSearchConnector(
                yandex_stored[1]["api_key"], yandex_stored[1]["folder_id"]
            )
        plan = SearchPlanData.model_validate(job.plan.structured_plan)
        records = []
        for query in plan.industry_queries:
            records.extend(await dadata.search(query, plan.city, 20))
        unique_records = {record.inn or normalize_name(record.name): record for record in records}
        companies: list[Company] = []
        for record in unique_records.values():
            company, _ = await _save_company_from_record(session, job, record)
            companies.append(company)
        await session.commit()
        if await _check_cancel(session, job):
            return
        job.stage = "websites"
        job.progress = 45
        await session.commit()
        gateway = await _gigachat(session)
        for index, company in enumerate(companies):
            try:
                site = await _discover_site(yandex, company)
                if site:
                    facts, verified = await _crawl_and_score(session, company, site)
                    if verified:
                        company.website = site
                        await session.flush()
                        await generate_opportunities(session, gateway, company, facts)
                        await session.commit()
            except Exception as exc:
                job.status = JobStatus.partial
                job.error = f"{company.name}: {str(exc)[:500]}"
                await session.commit()
            job.progress = min(90, 50 + int((index + 1) / max(len(companies), 1) * 40))
            await session.commit()
            if await _check_cancel(session, job):
                return
        job.status = JobStatus.completed if job.status != JobStatus.partial else JobStatus.partial
        job.stage = "completed"
        job.progress = 100
        session.add(
            AuditEvent(action="research_completed", entity_type="search_job", entity_id=job.id)
        )
        await session.commit()
    except Exception as exc:
        job.status = JobStatus.failed
        job.stage = "failed"
        job.error = str(exc)[:1000]
        await session.commit()
