"""Ranking and scoring.

Two deterministic scores drive the screener:

* **Confidence (0-100)** -- how good *this* setup is: a volume-primary blend of
  volume quality, MA-trend quality, setup family, and reward/risk asymmetry.
  Capital preservation is built in: anything without a valid, asymmetric plan
  scores zero.
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
from src.config import SIGNAL_MODEL_MA_DC_VOLUME_REGIME
from src.screener.setups import AVOID, BREAKOUT, Setup, setup_quality
from src.screener.strategy import StrategyConfig
from src.screener.trade_plan import TradePlan
from src.utils.numeric import clamp

DISTRIBUTION_DISCOUNT = 0.90  # multiplier applied when up/down volume < 1.0


def sector_trend_score(
    ticker_return: float, peer_returns: tuple[float, ...], market_return: float
) -> float:
    """Normalize a stock's peer-group leadership signal from 0..1.

    This is a real market-derived proxy for industry strength: a name that is
    beating its sector median and the broader tape while its peers are also
    trending higher receives a higher score. It is not external news sentiment;
    it is data-driven leadership and breadth.
    """
    if not peer_returns:
        return 0.0
    peer_median = float(pd.Series(peer_returns).median())
    sector_breadth = float(sum(r > market_return for r in peer_returns) / len(peer_returns))
    sector_momentum = clamp((peer_median - market_return + 0.10) / 0.25)
    relative_lead = clamp((ticker_return - peer_median + 0.10) / 0.20)
    score = 0.55 * sector_momentum + 0.45 * relative_lead + 0.10 * sector_breadth
    return clamp(score)


def regime_suppresses_entry(signal_model: str, risk_on: bool, setup_type: str) -> bool:
    """Whether the regime-aware model drops this entry.

    Edge attribution showed risk-off breakouts are negative-EV for the volume
    model (~-0.02R over 10y) while risk-off pullbacks stay positive (~+0.30R).
    So the regime-aware variant suppresses *only* risk-off breakouts, leaving the
    profitable risk-on book and risk-off pullbacks untouched.
    """
    return (
        signal_model == SIGNAL_MODEL_MA_DC_VOLUME_REGIME and not risk_on and setup_type == BREAKOUT
    )


# Volume-primary confidence weights. Sum to 1.0 across the scoring components.
# We add a lightweight industry/trend contribution so relative strength and
# recent breadth help rank leaders without turning the model into a noisy
# all-signal blender.
VOLUME_CONFIDENCE_WEIGHTS = {
    'volume': 0.35,
    'trend': 0.20,
    'reward': 0.15,
    'setup': 0.15,
    'industry': 0.15,
}


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
    sector_strength: float = 0.0,
) -> float:
    if setup.setup_type == AVOID or plan.entry is None or plan.reward_risk is None:
        return 0.0
    return _confidence_ma_dc_volume(features, setup, plan, config, sector_strength)


def _confidence_ma_dc_volume(
    features: MarketFeatures,
    setup: Setup,
    plan: TradePlan,
    config: StrategyConfig,
    sector_strength: float = 0.0,
) -> float:
    """Volume-primary confidence.

    Weights volume most heavily, then MA-trend quality, reward/risk asymmetry,
    and setup family -- so the score reflects only MA + Donchian + volume.
    """
    components = {
        'volume': _volume_confidence_component(features),
        'trend': features.trend_score,
        'reward': _reward_component(plan.reward_risk, config),
        'setup': setup_quality(features, setup),
        'industry': _industry_trend_component(features, sector_strength),
    }
    score = sum(VOLUME_CONFIDENCE_WEIGHTS[name] * value for name, value in components.items())
    if features.updown_volume_ratio < 1.0:
        score *= DISTRIBUTION_DISCOUNT
    return round(100 * clamp(score), 1)


def _volume_confidence_component(features: MarketFeatures) -> float:
    """Blend relative volume, up/down accumulation, and OBV slope (all 0..1)."""
    surge = clamp((features.rel_volume - 0.8) / 0.9)  # 0 at ~0.8x, 1 at ~1.7x
    accumulation = clamp((features.updown_volume_ratio - 0.8) / 0.9)  # 0 at ~0.8, 1 at ~1.7
    obv = clamp(features.obv_slope / 0.10)
    return 0.5 * surge + 0.3 * accumulation + 0.2 * obv


def _industry_trend_component(features: MarketFeatures, sector_strength: float = 0.0) -> float:
    """Proxy for market/industry leadership from relative strength and breadth.

    This is intentionally lightweight: it reinforces names leading the tape and
    their peer group without introducing an external-news dependency.
    """
    relative_strength = clamp((features.rs_outperformance + 0.20) / 0.80)
    breadth = clamp((features.return_3m + 0.15) / 0.65)
    sector_component = clamp(sector_strength)
    return 0.45 * relative_strength + 0.30 * breadth + 0.25 * sector_component


def composite_rank(confidence: float, context: MarketContext) -> float:
    """Confidence tilted by the market regime (risk-on amplifies, risk-off damps)."""
    return round(confidence * (0.7 + 0.3 * context.score), 2)


def _reward_component(reward_risk: float, config: StrategyConfig) -> float:
    # min_reward_risk is the gate (>1); guard the degenerate ==1 config.
    span = config.min_reward_risk - 1.0
    if span <= 0:
        return 1.0 if reward_risk > 1.0 else 0.0
    return clamp((reward_risk - 1.0) / span)
