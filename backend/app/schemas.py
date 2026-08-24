import math
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class SearchRequest(BaseModel):
    query: str = Field(min_length=8, max_length=2000)
    city: str | None = Field(default=None, max_length=160)
    region: str | None = Field(default=None, max_length=160)
    federal_district: str | None = Field(default=None, max_length=160)
    target_roles: list[str] = Field(default_factory=list, max_length=20)


class SearchPlanData(BaseModel):
    industry_queries: list[str] = Field(min_length=1, max_length=8)
    city: str | None = None
    region: str | None = None
    federal_district: str | None = None
    company_features: list[str] = Field(default_factory=list, max_length=20)
    exclusions: list[str] = Field(default_factory=list, max_length=20)
    target_roles: list[str] = Field(default_factory=list, max_length=20)
    sources: list[Literal["dadata", "yandex_search", "official_site"]]
    actions: list[str] = Field(min_length=1, max_length=20)


class PlanResponse(BaseModel):
    plan: SearchPlanData
    connected_sources: dict[str, bool]


class JobResponse(BaseModel):
    id: str
    query: str
    city: str | None
    region: str | None
    federal_district: str | None
    target_roles: list[str]
    status: str
    progress: int
    stage: str
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ServiceSignalInput(BaseModel):
    kind: Literal["positive", "negative"]
    text: str = Field(min_length=2, max_length=1000)


class ServiceInput(BaseModel):
    name: str = Field(min_length=2, max_length=300)
    description: str = Field(min_length=2, max_length=5000)
    category: str = Field(min_length=2, max_length=100)
    target_industries: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    min_company_size: int | None = Field(default=None, ge=0)
    max_company_size: int | None = Field(default=None, ge=0)
    geography: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    business_value: list[str] = Field(default_factory=list)
    price_range: str | None = Field(default=None, max_length=160)
    priority: int = Field(default=50, ge=0, le=100)
    is_active: bool = True
    signals: list[ServiceSignalInput] = Field(default_factory=list)

    @field_validator("max_company_size")
    @classmethod
    def validate_size(cls, value: int | None, info: Any) -> int | None:
        minimum = info.data.get("min_company_size")
        if value is not None and minimum is not None and value < minimum:
            raise ValueError("Максимальный размер меньше минимального")
        return value


class ConnectorInput(BaseModel):
    is_enabled: bool
    rate_limit_per_minute: int = Field(default=30, ge=1, le=600)
    config: dict[str, str] = Field(default_factory=dict)


class GigaChatInput(BaseModel):
    authorization_key: str | None = Field(default=None, min_length=10)
    scope: Literal["GIGACHAT_API_PERS", "GIGACHAT_API_B2B", "GIGACHAT_API_CORP"] = (
        "GIGACHAT_API_PERS"
    )
    model: str = Field(default="GigaChat-2", max_length=100)
    base_url: HttpUrl = HttpUrl("https://gigachat.devices.sberbank.ru/api/v1")
    oauth_url: HttpUrl = HttpUrl("https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int = Field(default=3000, ge=100, le=32000)
    timeout_seconds: int = Field(default=30, ge=3, le=120)


class FeedbackInput(BaseModel):
    decision: Literal["accepted", "rejected", "edited"]
    edited_details: dict[str, Any] | None = None
    note: str | None = Field(default=None, max_length=2000)


class IcpRuleInput(BaseModel):
    factor: str
    operator: str = "matches"
    expected_value: Any
    weight: float = Field(default=1.0, gt=0)
    is_exclusion: bool = False
    evidence_required: bool = True


class PainTypeInput(BaseModel):
    name: str
    normalized_type: str
    funnel_stage: Literal["acquisition", "conversion", "handling", "retention", "analytics"]
    importance: float = Field(default=1.0, gt=0)
    qualification_questions: list[str] = Field(default_factory=list)


class SignalTypeInput(BaseModel):
    name: str
    normalized_type: str
    weight: float = Field(default=1.0, gt=0)
    decay_days: int = Field(default=120, ge=1, le=3650)
    is_hard_exclusion: bool = False


class SolutionFitRuleInput(BaseModel):
    pain_type_index: int | None = Field(default=None, ge=0)
    funnel_stage: str | None = None
    weight: float = Field(default=1.0, gt=0)
    required: bool = False
    explanation: str = ""


class ScoreWeightsInput(BaseModel):
    w_icp: float = Field(default=0.30, ge=0, le=1)
    w_pain: float = Field(default=0.25, ge=0, le=1)
    w_intent: float = Field(default=0.25, ge=0, le=1)
    w_solution: float = Field(default=0.20, ge=0, le=1)

    @field_validator("w_solution")
    @classmethod
    def weights_sum_to_one(cls, value: float, info: Any) -> float:
        values = [
            info.data.get("w_icp", 0),
            info.data.get("w_pain", 0),
            info.data.get("w_intent", 0),
            value,
        ]
        if not math.isclose(sum(values), 1.0, abs_tol=1e-6):
            raise ValueError("Сумма весов должна равняться 1")
        return value


class SalesProfileInput(BaseModel):
    business_models: list[Literal["B2B", "B2C", "mixed"]] = Field(default_factory=list)
    product_outcome: str = Field(min_length=3)
    solved_funnel_stages: list[str] = Field(default_factory=list)
    required_traits: list[str] = Field(default_factory=list)
    desired_traits: list[str] = Field(default_factory=list)
    contraindications: list[str] = Field(default_factory=list)
    decision_maker_rules: dict[str, list[str]] = Field(default_factory=dict)
    discovery_questions: list[str] = Field(default_factory=list)
    objections: list[dict[str, str]] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    reference_rules: dict[str, Any] = Field(default_factory=dict)
    minimum_sales_score: float = Field(default=60, ge=0, le=100)
    icp_rules: list[IcpRuleInput] = Field(default_factory=list)
    pain_types: list[PainTypeInput] = Field(default_factory=list)
    buying_signals: list[SignalTypeInput] = Field(default_factory=list)
    negative_signals: list[SignalTypeInput] = Field(default_factory=list)
    solution_fit_rules: list[SolutionFitRuleInput] = Field(default_factory=list)
    weights: ScoreWeightsInput = Field(default_factory=ScoreWeightsInput)


class DealUpdateInput(BaseModel):
    status: Literal[
        "new",
        "needs_research",
        "ready_to_contact",
        "contacted",
        "qualified",
        "not_a_fit",
        "postponed",
        "won",
        "lost",
    ]
    reason: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=5000)
    next_action: str | None = Field(default=None, max_length=2000)
    next_action_at: datetime | None = None


class CrawlTarget(BaseModel):
    url: HttpUrl
