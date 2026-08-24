from datetime import UTC, datetime, timedelta

import pytest

from app.models import BuyingSignalType, IcpRule, PainType, SolutionFitRule
from app.opportunities import (
    IcpMatch,
    PainMatch,
    ServiceClassification,
    SignalMatch,
    calculate_scores,
    geometric_score,
    time_decay,
)


def test_time_decay_uses_configured_half_life() -> None:
    now = datetime.now(UTC)
    assert time_decay(now - timedelta(days=120), 120, now) == pytest.approx(0.5)
    assert time_decay(now - timedelta(days=240), 120, now) == pytest.approx(0.25)


def test_geometric_score_rejects_invalid_weights_and_zero_dimension() -> None:
    with pytest.raises(ValueError, match="Сумма весов"):
        geometric_score({"icp": 80, "pain": 70}, {"icp": 0.8, "pain": 0.8})
    assert geometric_score({"icp": 80, "pain": 0}, {"icp": 0.5, "pain": 0.5}) == 0


def test_sales_scores_are_deterministic_and_explainable() -> None:
    now = datetime.now(UTC)
    icp = IcpRule(id="icp-1", factor="B2B", expected_value=True, weight=1)
    pain = PainType(id="pain-1", name="Потери лидов", normalized_type="lead_loss", importance=1)
    signal = BuyingSignalType(
        id="signal-1", name="Новый сайт", normalized_type="new_site", weight=1, decay_days=120
    )
    fit = SolutionFitRule(id="fit-1", pain_type_id="pain-1", weight=1, required=True)
    classification = ServiceClassification(
        service_id="service-1",
        summary="Подтверждено источниками",
        icp_matches=[
            IcpMatch(
                rule_id="icp-1",
                matched=True,
                evidence_ids=["ev-1"],
                confidence=90,
                status="confirmed",
                reasoning_summary="B2B указан на сайте",
            )
        ],
        pains=[
            PainMatch(
                pain_type_id="pain-1",
                impact="high",
                evidence_ids=["ev-1"],
                confidence=80,
                status="confirmed",
                reasoning_summary="Есть подтверждённый разрыв",
            )
        ],
        buying_signals=[
            SignalMatch(
                signal_type_id="signal-1",
                observed_at=now,
                evidence_ids=["ev-1"],
                confidence=90,
                status="confirmed",
                reasoning_summary="Свежий сигнал",
            )
        ],
        negative_signals=[],
    )
    scores = calculate_scores(
        classification,
        [icp],
        {pain.id: pain},
        {signal.id: signal},
        {},
        [fit],
        {"icp": 0.3, "pain": 0.25, "intent": 0.25, "solution": 0.2},
        {"ev-1": 95},
        False,
        now,
    )
    assert scores.icp == 100
    assert scores.pain == 80
    assert scores.intent == 90
    assert scores.solution == 72
    assert 0 < scores.total < 100
    assert {factor.dimension for factor in scores.factors} == {"icp", "pain", "intent", "solution"}
    assert all(factor.evidence_id == "ev-1" for factor in scores.factors)
