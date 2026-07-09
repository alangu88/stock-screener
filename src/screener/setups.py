"""Setup detection.

Classifies the most meaningful, *actionable* technical setup for a symbol from
its :class:`MarketFeatures`, using a volume-primary model:

* **Moving averages** define whether the primary trend is intact.
* **Donchian channel** levels define the actionable breakout / pullback.
* **Volume is the decisive confirmation** -- breakouts need a surge plus net
  accumulation; pullbacks must be quiet yet still show accumulation.
* When nothing is confirmed, say so -- quality over quantity.

This module makes the *decision*; it computes no prices.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.analysis.features import MarketFeatures
from src.screener.strategy import StrategyConfig

BREAKOUT = 'Breakout'
PULLBACK = 'Pullback'
AVOID = 'Avoid'

# --- Volume-primary detection thresholds ------------------------------------
# The model leads with volume: a Donchian/MA-aligned trend is a necessary
# filter, but a signal only fires when volume confirms it. Kept intentionally
# simple so the model stays interpretable.
BREAKOUT_VOLUME_SURGE_MULT = 1.5  # breakout day must exceed this x average
MIN_ACCUMULATION_RATIO = 1.0  # up/down volume must show net accumulation
QUIET_PULLBACK_VOLUME_MULT = 1.2  # pullback volume must stay below this x avg

# Relative quality of each setup family, weighted toward *realized* edge.
# Walk-forward backtests (full S&P 500, 5y, regime-on, conf>=75 / R:R>=2.5, with
# the structural target exit held constant) found Breakouts the strongest setup
# by a wide margin -- ExpR 0.84R vs 0.36R for Pullbacks across 305 vs 1647
# trades, with ~2.3x the Sharpe and profit factor (2.53 vs 1.54) and a higher
# win rate (45% vs 33%). Pullbacks remain the workhorse on volume. Breakout
# quality is therefore at parity with Pullbacks rather than discounted. Reversal
# was removed earlier for negative expectancy. These weights reflect that
# evidence; re-run scripts/research_setup.py to revisit. (Breakouts
# are the most regime-sensitive family, so this assumes the live risk-on gate
# stays on.)
SETUP_QUALITY = {
    PULLBACK: 0.88,
    BREAKOUT: 0.88,
    AVOID: 0.0,
}

# A Pullback that has slipped below its rising trend EMA (it fell to the slower
# MA instead of holding the fast one) gave back roughly half its expectancy in
# walk-forward tests (0.19R vs 0.31-0.39R for pullbacks holding above the EMA,
# ~1,450 vs ~1,990 trades). Discount its setup quality so the weaker variant is
# ranked down and filtered by the confidence gate rather than treated as equal.
PULLBACK_BELOW_EMA_PENALTY = 0.7

# A constructive Pullback contracts toward support. One whose short-term
# volatility is still EXPANDING (short/long ATR > ~1.25) is not an orderly dip --
# over a 10y S&P 500 replay these realized ~0.07R (26% win) versus ~0.4-0.75R for
# pullbacks that were contracting. Demote them; this is orthogonal to the
# below-EMA penalty (a measure of volatility, not location).
PULLBACK_EXPANDING_VOL_RATIO = 1.25
PULLBACK_EXPANDING_VOL_PENALTY = 0.85

# Breakouts confirm on volume, and surge magnitude is a clean, monotonic edge
# predictor: over a 10y S&P 500 replay, breakouts on < ~1.7x average volume
# realized ~0.46-0.53R versus ~0.77R above it (win 36% vs 45%). A marginal-volume
# breakout (just clearing the breakout_volume_mult gate) is the weak cohort, so
# discount it; strong-volume breakouts keep full setup quality.
BREAKOUT_STRONG_VOLUME_MULT = 1.7
BREAKOUT_WEAK_VOLUME_PENALTY = 0.85

# Independently of volume, breakouts clearing into 52-week-high territory (no
# overhead supply) realized ~1.0R versus ~0.63R for those breaking a lower pivot
# while still >~1% below the prior high (10y S&P 500, strong-volume subset).
# Demote breakouts that remain well below the 52-week high (overhead resistance).
BREAKOUT_NEAR_HIGH_PCT = -0.01
BREAKOUT_OVERHEAD_PENALTY = 0.90


def setup_quality(features: MarketFeatures, setup: Setup) -> float:
    """Setup-family quality, context-adjusted for realized-edge modifiers."""
    base = SETUP_QUALITY[setup.setup_type]
    if (
        setup.setup_type == PULLBACK
        and features.ema_trend
        and features.price < features.ema_trend
    ):
        base *= PULLBACK_BELOW_EMA_PENALTY
    if setup.setup_type == PULLBACK and features.contraction_ratio > PULLBACK_EXPANDING_VOL_RATIO:
        base *= PULLBACK_EXPANDING_VOL_PENALTY
    if setup.setup_type == BREAKOUT:
        if features.rel_volume < BREAKOUT_STRONG_VOLUME_MULT:
            base *= BREAKOUT_WEAK_VOLUME_PENALTY
        if features.pct_from_high < BREAKOUT_NEAR_HIGH_PCT:
            base *= BREAKOUT_OVERHEAD_PENALTY
    return base


@dataclass(frozen=True)
class Setup:
    setup_type: str
    reason: str
    factors: tuple[str, ...]
    risks: tuple[str, ...]


def detect_setup(features: MarketFeatures, config: StrategyConfig) -> Setup:
    """Classify the most actionable setup from a symbol's features."""
    return _detect_setup_ma_dc_volume(features, config)


def _detect_setup_ma_dc_volume(features: MarketFeatures, config: StrategyConfig) -> Setup:
    """Volume-primary model built on MA trend + Donchian channel breaks.

    * **Moving averages** define whether the primary trend is intact
      (price > fast MA > long MA, with a rising long MA). No trend, no trade.
    * **Donchian channel** (the ``breakout_window``-day prior high, already the
      ``pivot``) defines the actionable level: a clean channel breakout or a
      pullback holding above the long MA while below the channel top.
    * **Volume is the decisive confirmation.** A breakout must arrive on a real
      volume surge *and* net accumulation; a pullback must be quiet (supply
      absorbed) yet still show accumulation and rising OBV. Volume failure
      demotes an otherwise-aligned chart to ``Avoid``.
    """
    f = features
    ma_uptrend = f.price > f.ma_fast > f.ma_long and f.ma_long_slope > 0

    breaking_out = f.pivot <= f.price <= f.pivot * (1 + config.extended_threshold)
    extended = f.price > f.pivot * (1 + config.extended_threshold)
    in_pullback = _in_pullback_zone(f, config)

    volume_surge = f.rel_volume >= BREAKOUT_VOLUME_SURGE_MULT
    accumulation = f.updown_volume_ratio >= MIN_ACCUMULATION_RATIO
    quiet_volume = f.rel_volume <= QUIET_PULLBACK_VOLUME_MULT
    obv_rising = f.obv_slope > 0

    if ma_uptrend and breaking_out and volume_surge and accumulation:
        return _breakout_volume(f, config)
    if ma_uptrend and in_pullback and quiet_volume and accumulation and obv_rising:
        return _pullback_volume(f, config)
    return _avoid_volume(f, config, ma_uptrend=ma_uptrend, extended=extended)


def _breakout_volume(f: MarketFeatures, config: StrategyConfig) -> Setup:
    factors = [
        f'Cleared the {config.breakout_window}-day Donchian high near {f.pivot:.2f}',
        f'Volume surge {f.rel_volume:.1f}x the {config.volume_window}-day average (primary trigger)',
        f'Up/down volume {f.updown_volume_ratio:.2f} confirms net accumulation',
        f'MA trend intact: price > {config.ma_fast}MA > {config.ma_long}MA (rising long MA)',
    ]
    risks = [
        'Breakouts can fail without follow-through; honor the stop below the channel',
    ]
    if f.obv_slope <= 0:
        risks.append('OBV not yet confirming — watch for a volume-less push')
    if f.atr_pct > 0.05:
        risks.append(f'Elevated volatility (ATR {f.atr_pct:.1%} of price)')
    return Setup(
        BREAKOUT, 'Volume-confirmed Donchian breakout in an MA uptrend',
        tuple(factors), tuple(risks),
    )


def _pullback_volume(f: MarketFeatures, config: StrategyConfig) -> Setup:
    factors = [
        f'Quiet pullback to support near the {config.ema_trend}EMA/{config.ma_fast}MA',
        f'Volume {f.rel_volume:.1f}x average — supply absorbed on the dip',
        f'Up/down volume {f.updown_volume_ratio:.2f} and rising OBV show accumulation',
        f'Uptrend intact (price above the {config.ma_long}MA)',
    ]
    risks = [
        'Support can break; invalidation sits below the recent swing low',
    ]
    return Setup(
        PULLBACK, 'Volume-backed pullback to rising support',
        tuple(factors), tuple(risks),
    )


def _avoid_volume(
    f: MarketFeatures, config: StrategyConfig, *, ma_uptrend: bool, extended: bool
) -> Setup:
    reasons = []
    if extended:
        reasons.append(f'Extended {((f.price - f.pivot) / f.pivot):+.1%} past the Donchian high -- chasing risk')
    if not ma_uptrend:
        reasons.append(f'MA trend not intact (need price > {config.ma_fast}MA > {config.ma_long}MA, rising long MA)')
    if f.updown_volume_ratio < MIN_ACCUMULATION_RATIO:
        reasons.append(f'Volume distribution (up/down volume {f.updown_volume_ratio:.2f} < 1.0)')
    if not reasons:
        reasons.append('No volume-confirmed trigger right now')
    return Setup(AVOID, '; '.join(reasons), (), ('Capital preservation: no volume-confirmed edge',))


def _in_pullback_zone(f: MarketFeatures, config: StrategyConfig) -> bool:
    near_ema = 0 <= (f.price - f.ema_trend) / f.ema_trend <= config.pullback_tolerance if f.ema_trend else False
    near_ma = 0 <= (f.price - f.ma_fast) / f.ma_fast <= config.pullback_tolerance if f.ma_fast else False
    below_pivot = f.price < f.pivot
    quiet = f.rel_volume < config.breakout_volume_mult
    return (near_ema or near_ma) and below_pivot and quiet
