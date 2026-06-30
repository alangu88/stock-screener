"""Setup detection.

Classifies the most meaningful, *actionable* technical setup for a symbol from
its :class:`MarketFeatures`. The taxonomy and priority order encode principles
shared by leadership-momentum and trend-following traders:

* Trade with the primary trend (Weinstein Stage 2, Minervini trend template).
* Demand relative-strength leadership (O'Neil RS, Minervini RS line).
* Prefer supply-drying-up structure: contractions and quiet pullbacks
  (Minervini VCP, Wyckoff accumulation, Darvas boxes).
* Require confirmation (volume expansion on breakouts) rather than prediction.
* When nothing is actionable, say so -- quality over quantity.

This module makes the *decision*; it computes no prices.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.analysis.features import MarketFeatures
from src.screener.strategy import StrategyConfig

BREAKOUT = 'Breakout'
CONTRACTION = 'Volatility Contraction'
PULLBACK = 'Pullback'
AVOID = 'Avoid'

# Relative quality of each setup family, weighted toward *realized* edge.
# Walk-forward backtests (full S&P 500, 5y, regime-on, conf>=75 / R:R>=2.5, with
# the structural target exit held constant) found Breakouts the strongest setup
# by a wide margin -- ExpR 0.84R vs 0.36R for Pullbacks across 305 vs 1647
# trades, with ~2.3x the Sharpe and profit factor (2.53 vs 1.54) and a higher
# win rate (45% vs 33%). Pullbacks remain the workhorse on volume; Contractions
# sit between. Breakout quality is therefore at parity with Pullbacks rather
# than discounted. Reversal was removed earlier for negative expectancy. These
# weights reflect that evidence; re-run scripts/backtest_stops.py --by-setup to
# revisit. (Breakouts are the most regime-sensitive family, so this assumes the
# live risk-on gate stays on.)
# Contraction is an anticipatory buy-stop, so it was historically discounted
# (0.84) for execution uncertainty. But simulating the buy-stop fill over a
# replay (enter when price clears the pivot within ~20 bars, else no trade)
# shows TRIGGERED contractions realize ~0.67-0.70R (10y/5y, S&P 500) -- robustly
# stronger than pullbacks (~0.32-0.42R) and close to breakouts (~0.72-0.93R).
# The discount was backwards, so contraction is raised to parity with the others.
SETUP_QUALITY = {
    PULLBACK: 0.88,
    BREAKOUT: 0.88,
    CONTRACTION: 0.88,
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
    f = features
    uptrend = f.trend_score >= 0.7 and f.price > f.ma_long
    rs_strong = f.rs_outperformance > 0
    contracting = f.contraction_ratio <= config.contraction_ratio

    pivot_gap = (f.pivot - f.price) / f.pivot if f.pivot else 0.0
    near_pivot_below = 0 < pivot_gap <= config.pivot_proximity
    breaking_out = f.pivot <= f.price <= f.pivot * (1 + config.extended_threshold)
    extended = f.price > f.pivot * (1 + config.extended_threshold)
    volume_breakout = f.rel_volume >= config.breakout_volume_mult
    in_pullback = _in_pullback_zone(f, config)

    if uptrend and rs_strong and breaking_out and volume_breakout:
        return _breakout(f, config)
    if uptrend and rs_strong and contracting and near_pivot_below:
        return _contraction(f, config)
    if uptrend and rs_strong and in_pullback:
        return _pullback(f, config)
    return _avoid(f, config, uptrend=uptrend, rs_strong=rs_strong, extended=extended)


def _in_pullback_zone(f: MarketFeatures, config: StrategyConfig) -> bool:
    near_ema = 0 <= (f.price - f.ema_trend) / f.ema_trend <= config.pullback_tolerance if f.ema_trend else False
    near_ma = 0 <= (f.price - f.ma_fast) / f.ma_fast <= config.pullback_tolerance if f.ma_fast else False
    below_pivot = f.price < f.pivot
    quiet = f.rel_volume < config.breakout_volume_mult
    return (near_ema or near_ma) and below_pivot and quiet


def _breakout(f: MarketFeatures, config: StrategyConfig) -> Setup:
    factors = [
        f'Broke above the {config.breakout_window}-day pivot near {f.pivot:.2f}',
        f'Volume {f.rel_volume:.1f}x the {config.volume_window}-day average confirms demand',
        f'Trend template {f.trend_score:.0%}; price above stacked 50/150/200 MAs',
        f'Leading the market ({f.rs_outperformance:+.1%} vs SPY)',
    ]
    if f.rs_line_new_high:
        factors.append('Relative-strength line at new highs (institutional leadership)')
    risks = [
        'Breakouts can fail without follow-through; honor the stop below the base',
    ]
    if f.base_depth > 0.20:
        risks.append(f'Base is deep ({f.base_depth:.0%}); stop distance is wider than ideal')
    if f.atr_pct > 0.05:
        risks.append(f'Elevated volatility (ATR {f.atr_pct:.1%} of price)')
    return Setup(BREAKOUT, 'Confirmed breakout from a base in a leading uptrend', tuple(factors), tuple(risks))


def _contraction(f: MarketFeatures, config: StrategyConfig) -> Setup:
    factors = [
        f'Volatility contracting (short/long ATR {f.contraction_ratio:.2f}) -- supply drying up',
        f'Coiled {((f.pivot - f.price) / f.pivot):.1%} under the {config.breakout_window}-day pivot {f.pivot:.2f}',
        f'Trend template {f.trend_score:.0%}; leading SPY ({f.rs_outperformance:+.1%})',
    ]
    if f.updown_volume_ratio > 1.2:
        factors.append(f'Up/down volume {f.updown_volume_ratio:.1f} shows quiet accumulation')
    risks = [
        'Anticipatory setup: only triggers if price clears the pivot on volume',
        'A failed breakout can reverse quickly; the buy-stop defines risk',
    ]
    return Setup(CONTRACTION, 'Volatility contraction coiling below a pivot', tuple(factors), tuple(risks))


def _pullback(f: MarketFeatures, config: StrategyConfig) -> Setup:
    factors = [
        f'Healthy pullback to support near the {config.ema_trend}EMA/{config.ma_fast}MA',
        f'Uptrend intact (trend template {f.trend_score:.0%})',
        f'Still leading SPY ({f.rs_outperformance:+.1%})',
        'Pullback on below-average volume (supply absorbed)',
    ]
    risks = [
        'Support can break; invalidation sits below the recent swing low',
    ]
    if f.rs_outperformance < 0.02:
        risks.append('Relative strength only marginally positive')
    return Setup(PULLBACK, 'Trend continuation pullback to rising support', tuple(factors), tuple(risks))


def _avoid(f: MarketFeatures, config: StrategyConfig, *, uptrend: bool, rs_strong: bool, extended: bool) -> Setup:
    reasons = []
    if extended:
        reasons.append(f'Extended {((f.price - f.pivot) / f.pivot):+.1%} past the pivot -- chasing risk')
    if not uptrend:
        reasons.append(f'Trend not confirmed (template {f.trend_score:.0%}, price vs 200MA)')
    if not rs_strong:
        reasons.append(f'Lagging the market ({f.rs_outperformance:+.1%} vs SPY)')
    if not reasons:
        reasons.append('No actionable entry trigger right now')
    return Setup(AVOID, '; '.join(reasons), (), ('Capital preservation: no edge identified',))
