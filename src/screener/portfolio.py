"""Core / Satellite portfolio construction.

Turns a flat list of screened candidates into an allocation plan built around a
classic core-satellite framework:

* **Core** -- durable trend-continuation leaders (the statistically strongest,
  lower-turnover edge in backtesting). The foundation of the book.
* **Satellite** -- higher-octane, more tactical plays (momentum ignitions,
  smaller/faster names) that seek extra return around the core.

Each candidate gets a *core-ness* score from its setup family, conviction
(confidence), size/liquidity (market cap) and trend persistence; names at or
above a threshold join the Core sleeve, the rest the Satellite sleeve. Within
each sleeve, positions are sized by **risk parity** -- equal risk budget per
name (inverse of entry-to-stop distance) -- tilted by confidence and capped to
limit single-name concentration. The result is a suggested weight and the share
of total capital each position puts at risk.

Pure and deterministic: everything is derived from an existing result frame, so
the engine, CSV export and UI stay in sync.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from src.config import Settings
from src.screener.setups import BREAKOUT, CONTRACTION, PULLBACK
from src.utils.numeric import clamp, is_nan

CORE = 'Core'
SATELLITE = 'Satellite'

# Columns this module appends to the result frame.
PORTFOLIO_COLUMNS = ('Sleeve', 'Core Score', 'Position Size %', 'Risk Contribution %')

# How "core-like" each setup family is. Trend continuation in established
# leaders is durable (core); breakouts are momentum ignitions traded more
# tactically (satellite). Backtesting backs this: pullbacks/contractions carried
# the robust edge while breakouts were noisier.
_SETUP_CORE = {
    PULLBACK: 0.90,
    CONTRACTION: 0.85,
    BREAKOUT: 0.25,
}


@dataclass(frozen=True)
class PortfolioConfig:
    core_allocation: float = 0.70          # share of capital for the Core sleeve
    satellite_allocation: float = 0.30     # share of capital for the Satellite sleeve
    core_score_threshold: float = 0.60     # core-ness >= this => Core sleeve
    max_position_weight: float = 0.10      # cap any single name at 10% of the book
    # Core-score component weights (sum to 1).
    weight_setup: float = 0.40
    weight_confidence: float = 0.20
    weight_market_cap: float = 0.20
    weight_trend: float = 0.20

    @classmethod
    def from_settings(cls, settings: Settings) -> PortfolioConfig:
        core = clamp(settings.core_allocation, 0.0, 1.0)
        return cls(
            core_allocation=core,
            satellite_allocation=round(1.0 - core, 4),
            core_score_threshold=settings.core_score_threshold,
            max_position_weight=settings.max_position_weight,
        )


def core_score(
    setup_type: str | None,
    confidence: float | None,
    market_cap: float | None,
    trend_score: float | None,
    config: PortfolioConfig,
) -> float:
    """Blend setup family, conviction, size/liquidity and trend into a 0..1 score."""
    setup_c = _SETUP_CORE.get(setup_type, 0.5)
    conf_c = clamp((confidence or 0.0) / 100.0)
    cap_c = _market_cap_core(market_cap)
    trend_c = clamp(trend_score if trend_score is not None and not is_nan(trend_score) else 0.0)
    score = (
        config.weight_setup * setup_c
        + config.weight_confidence * conf_c
        + config.weight_market_cap * cap_c
        + config.weight_trend * trend_c
    )
    return round(clamp(score), 4)


def assign_portfolio(df: pd.DataFrame, config: PortfolioConfig) -> pd.DataFrame:
    """Append sleeve, core score and risk-based position sizing to ``df``."""
    out = df.copy()
    if out.empty:
        for col in PORTFOLIO_COLUMNS:
            out[col] = pd.Series(dtype='object' if col == 'Sleeve' else 'float64')
        return out

    out['Core Score'] = [
        core_score(row.get('Setup'), row.get('Confidence'), row.get('Market Cap'), row.get('Trend Score'), config)
        for _, row in out.iterrows()
    ]
    out['Sleeve'] = [CORE if s >= config.core_score_threshold else SATELLITE for s in out['Core Score']]

    weights = pd.Series(0.0, index=out.index)
    for sleeve, allocation in ((CORE, config.core_allocation), (SATELLITE, config.satellite_allocation)):
        members = out.loc[out['Sleeve'] == sleeve]
        for idx, weight in _size_sleeve(members, allocation, config.max_position_weight).items():
            weights.at[idx] = weight

    out['Position Size %'] = weights.round(4)
    out['Risk Contribution %'] = (weights * out['Risk %'].fillna(0.0)).round(4)
    return out


def sleeve_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-sleeve roll-up: positions, capital allocated, risk taken, quality."""
    sleeves = [CORE, SATELLITE]
    rows = [_summary_row(name, df[df['Sleeve'] == name] if 'Sleeve' in df.columns else df.iloc[0:0])
            for name in sleeves]
    rows.append(_summary_row('Total', df))
    return pd.DataFrame(rows)


def _summary_row(name: str, sub: pd.DataFrame) -> dict:
    has = not sub.empty
    return {
        'Sleeve': name,
        'Positions': int(len(sub)),
        'Allocation %': float(sub['Position Size %'].sum()) if has else 0.0,
        'Portfolio Heat %': float(sub['Risk Contribution %'].sum()) if has else 0.0,
        'Avg Confidence': float(sub['Confidence'].mean()) if has else 0.0,
        'Avg R/R': float(sub['R/R'].mean()) if has else 0.0,
        'Avg Core Score': float(sub['Core Score'].mean()) if has else 0.0,
    }


def _size_sleeve(members: pd.DataFrame, allocation: float, cap: float) -> dict:
    """Risk-parity weights (inverse risk, confidence-tilted) with a per-name cap.

    Water-fills the allocation: any name whose proportional weight would exceed
    ``cap`` is pinned at the cap and the remaining capital is re-shared among the
    others. Names with a non-positive or missing stop distance are skipped.
    """
    raw: dict = {}
    for idx, row in members.iterrows():
        risk = row.get('Risk %')
        if risk is None or is_nan(risk) or risk <= 0:
            continue
        confidence = row.get('Confidence')
        tilt = float(confidence) if confidence is not None and not is_nan(confidence) and confidence > 0 else 1.0
        raw[idx] = tilt / float(risk)

    if not raw or allocation <= 0:
        return {}

    final: dict = {}
    remaining = allocation
    active = set(raw)
    for _ in range(len(raw) + 1):
        total = sum(raw[i] for i in active)
        if not active or total <= 0 or remaining <= 0:
            break
        over = [i for i in active if remaining * raw[i] / total > cap]
        if not over:
            for i in active:
                final[i] = remaining * raw[i] / total
            break
        for i in over:
            final[i] = cap
            active.discard(i)
            remaining -= cap
    return final


def _market_cap_core(market_cap: float | None) -> float:
    """Map market cap to 0..1 on a log scale: ~$1B -> 0, ~$1T -> 1."""
    if market_cap is None or is_nan(market_cap) or market_cap <= 0:
        return 0.4  # unknown size: lean slightly tactical, but not extreme
    return clamp((math.log10(market_cap) - 9.0) / 3.0)
