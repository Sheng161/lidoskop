import pytest
from pydantic import ValidationError

from app.schemas import SearchPlanData, ServiceInput


def test_plan_rejects_unapproved_source() -> None:
    with pytest.raises(ValidationError):
        SearchPlanData.model_validate(
            {
                "industry_queries": ["мебель"],
                "sources": ["linkedin"],
                "actions": ["найти компании"],
            }
        )


def test_service_rejects_inverted_size_range() -> None:
    with pytest.raises(ValidationError):
        ServiceInput(
            name="CRM",
            description="Внедрение CRM",
            category="automation",
            min_company_size=100,
            max_company_size=10,
        )
