from __future__ import annotations

from pytest import approx

from src.core.scoring import EntryQualityScorer, MultiFactorScorer


def test_multifactor_score_uses_weighted_pillars() -> None:
    scorer = MultiFactorScorer()
    result = scorer.score(
        fundamentals=82.0,
        sector=71.0,
        technical=88.0,
        volume_risk=76.0,
    )

    assert 0.0 <= result.total <= 100.0
    assert result.total == approx(80.70, abs=0.01)
    assert result.breakdown == {
        'fundamentals': 82.0,
        'sector': 71.0,
        'technical': 88.0,
        'volume_risk': 76.0,
    }


def test_entry_quality_includes_accumulation_distribution_signal() -> None:
    scorer = EntryQualityScorer()
    strong = scorer.score(
        trend_integrity=0.85,
        support_quality=0.8,
        volume_absorption=0.9,
        accumulation_distribution=0.9,
        relative_strength=0.8,
        risk_quality=0.75,
    )
    weak = scorer.score(
        trend_integrity=0.4,
        support_quality=0.3,
        volume_absorption=0.3,
        accumulation_distribution=0.2,
        relative_strength=0.3,
        risk_quality=0.2,
    )

    assert strong.total >= 75.0
    assert strong.verdict == 'Strong dip'
    assert strong.breakdown['accumulation_distribution'] > 80.0
    assert weak.verdict == 'Distribution trap'
    assert weak.breakdown['accumulation_distribution'] < 40.0


def test_multifactor_score_clamps_extremes() -> None:
    scorer = MultiFactorScorer()
    low = scorer.score(fundamentals=0.0, sector=0.0, technical=0.0, volume_risk=0.0)
    high = scorer.score(fundamentals=100.0, sector=100.0, technical=100.0, volume_risk=100.0)

    assert low.total == 0.0
    assert high.total == 100.0


def test_entry_quality_distinguishes_good_pullback_from_distribution_trap() -> None:
    scorer = EntryQualityScorer()
    strong = scorer.score(
        trend_integrity=0.9,
        support_quality=0.8,
        volume_absorption=0.85,
        relative_strength=0.82,
        risk_quality=0.75,
    )
    weak = scorer.score(
        trend_integrity=0.35,
        support_quality=0.25,
        volume_absorption=0.2,
        relative_strength=0.3,
        risk_quality=0.2,
    )

    assert strong.total >= 75.0
    assert strong.verdict == 'Strong dip'
    assert weak.total < 40.0
    assert weak.verdict == 'Distribution trap'
