"""Ranking and scoring.

Two deterministic scores drive the screener:

* **Confidence (0-100)** -- how good *this* setup is, blending trend quality,
  relative strength, setup family, accumulation/volume, volatility contraction,
  and reward/risk asymmetry. Capital preservation is built in: anything without
  a valid, asymmetric plan scores zero.
* **Composite rank** -- confidence scaled by the broad-market regime, so the
  same setup ranks higher in a healthy tape than in a hostile one.

Keeping these separate from detection and planning means the methodology can be
re-weighted without touching the trade logic.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.analysis.features import MarketFeatures
from src.analysis.indicators import slope_pct, sma
from src.screener.setups import AVOID, Setup, setup_quality
from src.screener.strategy import StrategyConfig
from src.screener.trade_plan import TradePlan
from src.utils.numeric import clamp

RS_NORM = 0.15  # +/-15% blended outperformance spans the 0..1 RS scale
DISTRIBUTION_DISCOUNT = 0.90  # multiplier applied when up/down volume < 1.0


@dataclass(frozen=True)
class MarketContext:
    score: float  # 0..1
    label: str


def assess_market_context(benchmark_close: pd.Series, config: StrategyConfig) -> MarketContext:
    close = benchmark_close.dropna()
    if len(close) < config.ma_long:
        return MarketContext(0.5, 'Neutral')
    price = float(close.iloc[-1])
    ma_fast = float(sma(close, config.ma_fast).iloc[-1])
    ma_long = float(sma(close, config.ma_long).iloc[-1])
    long_slope = slope_pct(sma(close, config.ma_long), config.slope_lookback)
    conditions = (price > ma_long, ma_fast > ma_long, long_slope > 0, price > ma_fast)
    score = sum(conditions) / len(conditions)
    label = 'Risk-On' if score >= 0.75 else 'Risk-Off' if score < 0.4 else 'Neutral'
    return MarketContext(score, label)


def confidence_score(
    features: MarketFeatures,
    setup: Setup,
    plan: TradePlan,
    config: StrategyConfig,
) -> float:
    if setup.setup_type == AVOID or plan.entry is None or plan.reward_risk is None:
        return 0.0

    components = {
        'trend': features.trend_score,
        'rs': _relative_strength_component(features),
        'setup': setup_quality(features, setup),
        'volume': _volume_component(features),
        'contraction': _contraction_component(features.contraction_ratio),
        'reward': _reward_component(plan.reward_risk, config),
    }
    weights = config.confidence_weights
    score = sum(weights[name] * value for name, value in components.items())
    # Net distribution (more down- than up-volume) is a red flag that roughly
    # halved realized expectancy in backtests; discount the score rather than
    # zero it, so a strong setup under light distribution can still qualify.
    if features.updown_volume_ratio < 1.0:
        score *= DISTRIBUTION_DISCOUNT
    return round(100 * clamp(score), 1)


def composite_rank(confidence: float, context: MarketContext) -> float:
    """Confidence tilted by the market regime (risk-on amplifies, risk-off damps)."""
    return round(confidence * (0.7 + 0.3 * context.score), 2)


def _relative_strength_component(features: MarketFeatures) -> float:
    base = clamp((features.rs_outperformance + RS_NORM) / (2 * RS_NORM))
    if features.rs_line_new_high:
        base = clamp(base + 0.1)
    return base


def _volume_component(features: MarketFeatures) -> float:
    accumulation = clamp(features.updown_volume_ratio - 1.0)
    obv = clamp(features.obv_slope / 0.10)
    return 0.6 * accumulation + 0.4 * obv


def _contraction_component(contraction_ratio: float) -> float:
    # ratio 0.7 -> ~1.0 (tight), ratio 1.1 -> 0.0 (expanding)
    return clamp((1.1 - contraction_ratio) / 0.4)


def _reward_component(reward_risk: float, config: StrategyConfig) -> float:
    # min_reward_risk is the gate (>1); guard the degenerate ==1 config.
    span = config.min_reward_risk - 1.0
    if span <= 0:
        return 1.0 if reward_risk > 1.0 else 0.0
    return clamp((reward_risk - 1.0) / span)
