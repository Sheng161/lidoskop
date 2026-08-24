import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class JobStatus(enum.StrEnum):
    draft = "draft"
    queued = "queued"
    running = "running"
    partial = "partial"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class PersonStatus(enum.StrEnum):
    confirmed = "confirmed"
    probable = "probable"
    unverified = "unverified"
    outdated = "outdated"


class DealStatus(enum.StrEnum):
    new = "new"
    needs_research = "needs_research"
    ready_to_contact = "ready_to_contact"
    contacted = "contacted"
    qualified = "qualified"
    not_a_fit = "not_a_fit"
    postponed = "postponed"
    won = "won"
    lost = "lost"


class SearchJob(Base, TimestampMixin):
    __tablename__ = "search_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    query: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(160))
    region: Mapped[str | None] = mapped_column(String(160))
    federal_district: Mapped[str | None] = mapped_column(String(160))
    target_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.draft)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(100), default="draft")
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    plan: Mapped["SearchPlan | None"] = relationship(back_populates="job", uselist=False)


class SearchPlan(Base, TimestampMixin):
    __tablename__ = "search_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("search_jobs.id", ondelete="CASCADE"), unique=True
    )
    structured_plan: Mapped[dict[str, Any]] = mapped_column(JSON)
    prompt_version: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    job: Mapped[SearchJob] = relationship(back_populates="plan")


class Company(Base, TimestampMixin):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(500))
    normalized_name: Mapped[str] = mapped_column(String(500), index=True)
    inn: Mapped[str | None] = mapped_column(String(12), unique=True)
    ogrn: Mapped[str | None] = mapped_column(String(15), unique=True)
    legal_form: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str | None] = mapped_column(String(80))
    website: Mapped[str | None] = mapped_column(String(2048))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("search_jobs.id", ondelete="SET NULL"))
    names: Mapped[list["CompanyName"]] = relationship(cascade="all, delete-orphan")
    addresses: Mapped[list["Address"]] = relationship(cascade="all, delete-orphan")
    people: Mapped[list["Person"]] = relationship(cascade="all, delete-orphan")
    resources: Mapped[list["Resource"]] = relationship(cascade="all, delete-orphan")
    scores: Mapped[list["DigitalPresenceScore"]] = relationship(cascade="all, delete-orphan")
    opportunities: Mapped[list["SalesOpportunity"]] = relationship(cascade="all, delete-orphan")


class CompanyName(Base, TimestampMixin):
    __tablename__ = "company_names"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    value: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(30), default="official")
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"))


class Address(Base, TimestampMixin):
    __tablename__ = "addresses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))
    full_address: Mapped[str] = mapped_column(Text)
    federal_district: Mapped[str | None] = mapped_column(String(160))
    region: Mapped[str | None] = mapped_column(String(160))
    city: Mapped[str | None] = mapped_column(String(160))
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"))


class Person(Base, TimestampMixin):
    __tablename__ = "people"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    full_name: Mapped[str] = mapped_column(String(300))
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    confidence_reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[PersonStatus] = mapped_column(
        Enum(PersonStatus), default=PersonStatus.unverified
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    positions: Mapped[list["Position"]] = relationship(cascade="all, delete-orphan")
    contacts: Mapped[list["Contact"]] = relationship(cascade="all, delete-orphan")


class Position(Base, TimestampMixin):
    __tablename__ = "positions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    person_id: Mapped[str] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"))
    normalized_title: Mapped[str] = mapped_column(String(200))
    raw_title: Mapped[str] = mapped_column(String(300))
    period: Mapped[str | None] = mapped_column(String(120))
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"))


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    person_id: Mapped[str | None] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"))
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))
    value: Mapped[str] = mapped_column(String(500))
    origin: Mapped[str] = mapped_column(String(80))
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    technical_status: Mapped[str] = mapped_column(String(40), default="not_checked")
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"))


class Evidence(Base, TimestampMixin):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(80))
    source_url: Mapped[str] = mapped_column(String(2048))
    page_title: Mapped[str | None] = mapped_column(String(500))
    excerpt: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(100))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confidence: Mapped[int] = mapped_column(Integer, default=100)


class Resource(Base, TimestampMixin):
    __tablename__ = "resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(80))
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(500))
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"))
    confidence: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(String(30), default="current")
    __table_args__ = (UniqueConstraint("company_id", "url", name="uq_company_resource_url"),)


class Relationship(Base, TimestampMixin):
    __tablename__ = "relationships"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_type: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[str] = mapped_column(String(36))
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(36))
    relation: Mapped[str] = mapped_column(String(80))
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"))
    confidence: Mapped[int] = mapped_column(Integer, default=100)


class DigitalPresenceScore(Base, TimestampMixin):
    __tablename__ = "digital_presence_scores"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    total: Mapped[float] = mapped_column(Float)
    version: Mapped[str] = mapped_column(String(40), default="v1")
    factors: Mapped[list["ScoreFactor"]] = relationship(cascade="all, delete-orphan")


class ScoreFactor(Base, TimestampMixin):
    __tablename__ = "score_factors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    score_id: Mapped[str] = mapped_column(
        ForeignKey("digital_presence_scores.id", ondelete="CASCADE")
    )
    category: Mapped[str] = mapped_column(String(100))
    weight: Mapped[float] = mapped_column(Float)
    points: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"))


class ServiceCatalog(Base, TimestampMixin):
    __tablename__ = "service_catalog"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100))
    target_industries: Mapped[list[str]] = mapped_column(JSON, default=list)
    exclusions: Mapped[list[str]] = mapped_column(JSON, default=list)
    min_company_size: Mapped[int | None] = mapped_column(Integer)
    max_company_size: Mapped[int | None] = mapped_column(Integer)
    geography: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    target_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    business_value: Mapped[list[str]] = mapped_column(JSON, default=list)
    price_range: Mapped[str | None] = mapped_column(String(160))
    priority: Mapped[int] = mapped_column(Integer, default=50)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    signals: Mapped[list["ServiceSignal"]] = relationship(cascade="all, delete-orphan")
    icp_profile: Mapped["IcpProfile | None"] = relationship(
        back_populates="service", cascade="all, delete-orphan", uselist=False
    )
    pain_types: Mapped[list["PainType"]] = relationship(cascade="all, delete-orphan")
    buying_signal_types: Mapped[list["BuyingSignalType"]] = relationship(
        cascade="all, delete-orphan"
    )
    negative_signal_types: Mapped[list["NegativeSignalType"]] = relationship(
        cascade="all, delete-orphan"
    )
    solution_fit_rules: Mapped[list["SolutionFitRule"]] = relationship(cascade="all, delete-orphan")


class ServiceSignal(Base, TimestampMixin):
    __tablename__ = "service_signals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    service_id: Mapped[str] = mapped_column(ForeignKey("service_catalog.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)


class IcpProfile(Base, TimestampMixin):
    __tablename__ = "icp_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("service_catalog.id", ondelete="CASCADE"), unique=True
    )
    business_models: Mapped[list[str]] = mapped_column(JSON, default=list)
    product_outcome: Mapped[str] = mapped_column(Text, default="")
    solved_funnel_stages: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_traits: Mapped[list[str]] = mapped_column(JSON, default=list)
    desired_traits: Mapped[list[str]] = mapped_column(JSON, default=list)
    contraindications: Mapped[list[str]] = mapped_column(JSON, default=list)
    decision_maker_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    discovery_questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    objections: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    materials: Mapped[list[str]] = mapped_column(JSON, default=list)
    reference_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    minimum_sales_score: Mapped[float] = mapped_column(Float, default=60.0)
    service: Mapped[ServiceCatalog] = relationship(back_populates="icp_profile")
    rules: Mapped[list["IcpRule"]] = relationship(cascade="all, delete-orphan")


class IcpRule(Base, TimestampMixin):
    __tablename__ = "icp_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("icp_profiles.id", ondelete="CASCADE"))
    factor: Mapped[str] = mapped_column(String(100))
    operator: Mapped[str] = mapped_column(String(30), default="matches")
    expected_value: Mapped[Any] = mapped_column(JSON)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    is_exclusion: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=True)


class PainType(Base, TimestampMixin):
    __tablename__ = "pain_types"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    service_id: Mapped[str] = mapped_column(ForeignKey("service_catalog.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(300))
    normalized_type: Mapped[str] = mapped_column(String(100))
    funnel_stage: Mapped[str] = mapped_column(String(40))
    importance: Mapped[float] = mapped_column(Float, default=1.0)
    qualification_questions: Mapped[list[str]] = mapped_column(JSON, default=list)


class BuyingSignalType(Base, TimestampMixin):
    __tablename__ = "buying_signal_types"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    service_id: Mapped[str] = mapped_column(ForeignKey("service_catalog.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(300))
    normalized_type: Mapped[str] = mapped_column(String(100))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    decay_days: Mapped[int] = mapped_column(Integer, default=120)


class NegativeSignalType(Base, TimestampMixin):
    __tablename__ = "negative_signal_types"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    service_id: Mapped[str] = mapped_column(ForeignKey("service_catalog.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(300))
    normalized_type: Mapped[str] = mapped_column(String(100))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    decay_days: Mapped[int] = mapped_column(Integer, default=180)
    is_hard_exclusion: Mapped[bool] = mapped_column(Boolean, default=False)


class SolutionFitRule(Base, TimestampMixin):
    __tablename__ = "solution_fit_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    service_id: Mapped[str] = mapped_column(ForeignKey("service_catalog.id", ondelete="CASCADE"))
    pain_type_id: Mapped[str | None] = mapped_column(
        ForeignKey("pain_types.id", ondelete="CASCADE")
    )
    funnel_stage: Mapped[str | None] = mapped_column(String(40))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str] = mapped_column(Text, default="")


class ScoreWeightProfile(Base, TimestampMixin):
    __tablename__ = "score_weight_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    service_id: Mapped[str | None] = mapped_column(
        ForeignKey("service_catalog.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(160), default="default")
    w_icp: Mapped[float] = mapped_column(Float, default=0.30)
    w_pain: Mapped[float] = mapped_column(Float, default=0.25)
    w_intent: Mapped[float] = mapped_column(Float, default=0.25)
    w_solution: Mapped[float] = mapped_column(Float, default=0.20)
    version: Mapped[str] = mapped_column(String(40), default="sales-v1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SalesOpportunity(Base, TimestampMixin):
    __tablename__ = "sales_opportunities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    service_id: Mapped[str] = mapped_column(ForeignKey("service_catalog.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    score: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[int] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default=DealStatus.new.value)
    evidence_links: Mapped[list["OpportunityEvidence"]] = relationship(cascade="all, delete-orphan")
    feedback: Mapped[list["OpportunityFeedback"]] = relationship(cascade="all, delete-orphan")
    calculations: Mapped[list["ScoreCalculation"]] = relationship(cascade="all, delete-orphan")
    playbooks: Mapped[list["SalesPlaybook"]] = relationship(cascade="all, delete-orphan")
    status_history: Mapped[list["DealStatusHistory"]] = relationship(cascade="all, delete-orphan")
    manager_notes: Mapped[list["ManagerNote"]] = relationship(cascade="all, delete-orphan")
    next_actions: Mapped[list["NextAction"]] = relationship(cascade="all, delete-orphan")


class CompanyPain(Base, TimestampMixin):
    __tablename__ = "company_pains"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    service_id: Mapped[str] = mapped_column(ForeignKey("service_catalog.id", ondelete="CASCADE"))
    pain_type_id: Mapped[str] = mapped_column(ForeignKey("pain_types.id", ondelete="CASCADE"))
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"))
    status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[int] = mapped_column(Integer)
    impact: Mapped[str] = mapped_column(String(20))
    explanation: Mapped[str] = mapped_column(Text)
    qualification_questions: Mapped[list[str]] = mapped_column(JSON, default=list)


class CompanyBuyingSignal(Base, TimestampMixin):
    __tablename__ = "company_buying_signals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    service_id: Mapped[str] = mapped_column(ForeignKey("service_catalog.id", ondelete="CASCADE"))
    signal_type_id: Mapped[str] = mapped_column(
        ForeignKey("buying_signal_types.id", ondelete="CASCADE")
    )
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)


class CompanyNegativeSignal(Base, TimestampMixin):
    __tablename__ = "company_negative_signals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    service_id: Mapped[str] = mapped_column(ForeignKey("service_catalog.id", ondelete="CASCADE"))
    signal_type_id: Mapped[str] = mapped_column(
        ForeignKey("negative_signal_types.id", ondelete="CASCADE")
    )
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)


class ScoreCalculation(Base):
    __tablename__ = "score_calculations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    service_id: Mapped[str] = mapped_column(ForeignKey("service_catalog.id", ondelete="CASCADE"))
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("sales_opportunities.id", ondelete="CASCADE")
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    icp_fit: Mapped[float] = mapped_column(Float)
    pain_score: Mapped[float] = mapped_column(Float)
    purchase_probability: Mapped[float] = mapped_column(Float)
    solution_fit: Mapped[float] = mapped_column(Float)
    sales_opportunity_score: Mapped[float] = mapped_column(Float)
    data_completeness: Mapped[float] = mapped_column(Float)
    evidence_confidence: Mapped[float] = mapped_column(Float)
    score_version: Mapped[str] = mapped_column(String(40))
    weight_snapshot: Mapped[dict[str, float]] = mapped_column(JSON)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    factors: Mapped[list["SalesOpportunityFactor"]] = relationship(cascade="all, delete-orphan")


class SalesOpportunityFactor(Base):
    __tablename__ = "sales_opportunity_factors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    calculation_id: Mapped[str] = mapped_column(
        ForeignKey("score_calculations.id", ondelete="CASCADE")
    )
    dimension: Mapped[str] = mapped_column(String(30))
    rule_type: Mapped[str] = mapped_column(String(60))
    rule_id: Mapped[str | None] = mapped_column(String(36))
    raw_value: Mapped[float] = mapped_column(Float)
    weighted_value: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"))


class SalesPlaybook(Base):
    __tablename__ = "sales_playbooks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("sales_opportunities.id", ondelete="CASCADE")
    )
    calculation_id: Mapped[str] = mapped_column(ForeignKey("score_calculations.id"))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    prompt_version: Mapped[str] = mapped_column(String(40), default="playbook-v1")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DealStatusHistory(Base):
    __tablename__ = "deal_status_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("sales_opportunities.id", ondelete="CASCADE")
    )
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ManagerNote(Base, TimestampMixin):
    __tablename__ = "manager_notes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("sales_opportunities.id", ondelete="CASCADE")
    )
    note: Mapped[str] = mapped_column(Text)


class NextAction(Base, TimestampMixin):
    __tablename__ = "next_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("sales_opportunities.id", ondelete="CASCADE")
    )
    action: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open")


class OpportunityEvidence(Base):
    __tablename__ = "opportunity_evidence"
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("sales_opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"), primary_key=True)


class OpportunityFeedback(Base, TimestampMixin):
    __tablename__ = "opportunity_feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("sales_opportunities.id", ondelete="CASCADE")
    )
    decision: Mapped[str] = mapped_column(String(30))
    edited_details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text)


class PromptVersion(Base, TimestampMixin):
    __tablename__ = "prompt_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    purpose: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(40))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(100))
    input_evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class SourceConnector(Base, TimestampMixin):
    __tablename__ = "source_connectors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(160))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    encrypted_config: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="not_connected")
    last_error: Mapped[str | None] = mapped_column(Text)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=30)


class ConnectorRun(Base, TimestampMixin):
    __tablename__ = "connector_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    connector_id: Mapped[str] = mapped_column(ForeignKey("source_connectors.id"))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("search_jobs.id"))
    status: Mapped[str] = mapped_column(String(30))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class CrawlPage(Base, TimestampMixin):
    __tablename__ = "crawl_pages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(2048))
    status_code: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    robots_allowed: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("company_id", "url", name="uq_crawl_company_url"),)


class Export(Base, TimestampMixin):
    __tablename__ = "exports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("search_jobs.id"))
    format: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(1000))
    row_count: Mapped[int] = mapped_column(Integer)


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    encrypted_value: Mapped[str | None] = mapped_column(Text)
    public_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
