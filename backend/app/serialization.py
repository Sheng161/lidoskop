from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Company, DigitalPresenceScore, Person, SalesOpportunity


async def company_detail(session: AsyncSession, company_id: str) -> dict[str, Any] | None:
    stmt = (
        select(Company)
        .where(Company.id == company_id)
        .options(
            selectinload(Company.addresses),
            selectinload(Company.people).selectinload(Person.positions),
            selectinload(Company.people).selectinload(Person.contacts),
            selectinload(Company.resources),
            selectinload(Company.scores).selectinload(DigitalPresenceScore.factors),
            selectinload(Company.opportunities).selectinload(SalesOpportunity.evidence_links),
        )
    )
    company = await session.scalar(stmt)
    if not company:
        return None
    return {
        "id": company.id,
        "name": company.name,
        "inn": company.inn,
        "ogrn": company.ogrn,
        "legal_form": company.legal_form,
        "status": company.status,
        "website": company.website,
        "addresses": [
            {
                "id": address.id,
                "kind": address.kind,
                "full_address": address.full_address,
                "region": address.region,
                "city": address.city,
                "evidence_id": address.evidence_id,
            }
            for address in company.addresses
        ],
        "people": [
            {
                "id": person.id,
                "full_name": person.full_name,
                "confidence": person.confidence,
                "confidence_reason": person.confidence_reason,
                "status": person.status.value,
                "positions": [
                    {
                        "raw_title": pos.raw_title,
                        "normalized_title": pos.normalized_title,
                        "evidence_id": pos.evidence_id,
                    }
                    for pos in person.positions
                ],
                "contacts": [
                    {
                        "kind": contact.kind,
                        "value": contact.value,
                        "origin": contact.origin,
                        "is_confirmed": contact.is_confirmed,
                        "technical_status": contact.technical_status,
                        "evidence_id": contact.evidence_id,
                    }
                    for contact in person.contacts
                ],
            }
            for person in company.people
        ],
        "resources": [
            {
                "id": resource.id,
                "kind": resource.kind,
                "url": resource.url,
                "title": resource.title,
                "confidence": resource.confidence,
                "evidence_id": resource.evidence_id,
            }
            for resource in company.resources
        ],
        "scores": [
            {
                "total": score.total,
                "version": score.version,
                "factors": [
                    {
                        "category": factor.category,
                        "weight": factor.weight,
                        "points": factor.points,
                        "explanation": factor.explanation,
                        "evidence_id": factor.evidence_id,
                    }
                    for factor in score.factors
                ],
            }
            for score in company.scores
        ],
        "opportunities": [
            {
                "id": opportunity.id,
                "service_id": opportunity.service_id,
                "title": opportunity.title,
                "score": opportunity.score,
                "confidence": opportunity.confidence,
                "priority": opportunity.priority,
                "summary": opportunity.summary,
                "details": opportunity.details,
                "status": opportunity.status,
                "evidence_ids": [link.evidence_id for link in opportunity.evidence_links],
            }
            for opportunity in company.opportunities
        ],
    }
