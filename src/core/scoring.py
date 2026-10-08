"""Multi-factor scoring primitives for the stock screener.

This module follows the architecture blueprint from the enhanced screener design:
separate the weighted scoring engine from the setup detection and trade-plan
logic, while retaining the repo's existing deterministic, testable structure.

The additional entry-quality model is intentionally concrete: it scores whether a
pullback is a quality dip into support or a distribution trap that should be
avoided. That is the practical upgrade that best matches the repo's trend-first
screening style.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactorScore:
    """Weighted multi-factor evaluation result."""

    total: float
    breakdown: dict[str, float]


@dataclass(frozen=True)
class EntryQualityScore:
    """Entry-quality readout for a pullback opportunity."""

    total: float
    verdict: str
    breakdown: dict[str, float]


class MultiFactorScorer:
    """Combine fundamentals, sector leadership, technical timing, and volume/risk."""

    _weights: dict[str, float] = {
        'fundamentals': 0.35,
        'sector': 0.20,
        'technical': 0.30,
        'volume_risk': 0.15,
    }

    @classmethod
    def _clamp(cls, value: float) -> float:
        return min(100.0, max(0.0, float(value)))

    def score(
        self,
        *,
        fundamentals: float,
        sector: float,
        technical: float,
        volume_risk: float,
    ) -> FactorScore:
        """Return a weighted score for the four scoring pillars.

        Each input is normalized to the 0..100 range before weighting, so a single
        poor pillar cannot dominate the final judgment and a strong pillar can
        compensate for a weaker one without violating the repo's continuous-score
        policy.
        """
        breakdown = {
            'fundamentals': self._clamp(fundamentals),
            'sector': self._clamp(sector),
            'technical': self._clamp(technical),
            'volume_risk': self._clamp(volume_risk),
        }

        total = sum(self._weights[name] * value for name, value in breakdown.items())

        return FactorScore(total=round(self._clamp(total), 2), breakdown=breakdown)


class EntryQualityScorer:
    """Score whether a pullback is strong support or a distribution trap.

    This is intentionally designed to reflect the best practice we want in the
    screener: buy the quality dip, not the deepest price. A healthy dip should
    show trend integrity, support retention, quiet or accumulating volume, and a
    favorable reward/risk profile.
    """

    _weights: dict[str, float] = {
        'trend_integrity': 0.25,
        'support_quality': 0.20,
        'volume_absorption': 0.15,
        'accumulation_distribution': 0.20,
        'relative_strength': 0.12,
        'risk_quality': 0.08,
    }

    @classmethod
    def _clamp(cls, value: float) -> float:
        return min(100.0, max(0.0, float(value)))

    def score(
        self,
        *,
        trend_integrity: float,
        support_quality: float,
        volume_absorption: float,
        accumulation_distribution: float = 0.6,
        relative_strength: float,
        risk_quality: float,
    ) -> EntryQualityScore:
        """Return a pullback-quality score and a plain-English verdict.

        The accumulation/distribution factor is the practical distinction between a
        healthy pullback into support and a distribution trap. Higher values mean the
        tape is absorbing supply and selling pressure is not overwhelming the trend.
        """
        breakdown = {
            'trend_integrity': self._clamp(trend_integrity * 100.0),
            'support_quality': self._clamp(support_quality * 100.0),
            'volume_absorption': self._clamp(volume_absorption * 100.0),
            'accumulation_distribution': self._clamp(accumulation_distribution * 100.0),
            'relative_strength': self._clamp(relative_strength * 100.0),
            'risk_quality': self._clamp(risk_quality * 100.0),
        }
        total = sum(self._weights[name] * value for name, value in breakdown.items())
        total = round(self._clamp(total), 2)

        if total >= 75.0:
            verdict = 'Strong dip'
        elif total >= 50.0:
            verdict = 'Neutral dip'
        elif total >= 35.0:
            verdict = 'Weak dip'
        else:
            verdict = 'Distribution trap'

        return EntryQualityScore(total=total, verdict=verdict, breakdown=breakdown)
