"""Feature engineering layer.

Turns raw OHLCV (plus a benchmark close series) into a single, deterministic
``MarketFeatures`` snapshot describing trend, relative strength, structure,
volatility, and accumulation for the most recent bar. This module performs the
*calculations* only; it makes no trading decisions.

Missing intraday data (High/Low) is handled explicitly by falling back to the
close, so the layer works with close-only feeds without raising.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.analysis.indicators import (
    atr,
    ema,
    on_balance_volume,
    rolling_high,
    rolling_low,
    slope_pct,
    sma,
)
from src.analysis.relative_strength import (
    blended_outperformance,
    rs_line_at_high,
)
from src.screener.strategy import StrategyConfig

MIN_BARS = 60


@dataclass(frozen=True)
class MarketFeatures:
    price: float

    # Trend structure
    ma_fast: float
    ma_mid: float
    ma_long: float
    ema_trend: float
    ma_long_slope: float
    ma_mid_slope: float
    stacked: bool
    trend_score: float  # 0..1 fraction of trend-template conditions met

    # 52-week positioning
    high_52w: float
    low_52w: float
    pct_from_high: float  # <= 0, distance below the high
    pct_above_low: float

    # Relative strength
    rs_outperformance: float
    rs_line_new_high: bool

    # Structure / levels
    pivot: float
    recent_high: float
    pivot_low: float  # low of the most recent contraction (tight stop reference)
    base_high: float
    base_low: float
    base_depth: float  # (base_high - base_low) / base_high

    # Volatility
    atr: float
    atr_pct: float
    contraction_ratio: float  # short ATR / long ATR (< 1 = contracting)

    # Volume / accumulation
    avg_volume: float
    rel_volume: float
    updown_volume_ratio: float
    obv_slope: float


def compute_features(
    df: pd.DataFrame | None,
    benchmark_close: pd.Series,
    config: StrategyConfig,
) -> MarketFeatures | None:
    """Build a :class:`MarketFeatures` snapshot or ``None`` if data is unusable."""
    if df is None or df.empty or 'Close' not in df.columns or 'Volume' not in df.columns:
        return None

    close = df['Close'].dropna()
    if len(close) < MIN_BARS:
        return None

    high = _ohlc_series(df, 'High', close)
    low = _ohlc_series(df, 'Low', close)
    volume = df['Volume'].reindex(close.index).fillna(0.0)

    price = float(close.iloc[-1])
    ma_fast = _last(sma(close, config.ma_fast), price)
    ma_mid = _last(sma(close, config.ma_mid), price)
    ma_long = _last(sma(close, config.ma_long), price)
    ema_trend = _last(ema(close, config.ema_trend), price)
    ma_long_slope = slope_pct(sma(close, config.ma_long), config.slope_lookback)
    ma_mid_slope = slope_pct(sma(close, config.ma_mid), config.slope_lookback)

    high_52w = float(rolling_high(high, config.high_low_window).iloc[-1])
    low_52w = float(rolling_low(low, config.high_low_window).iloc[-1])
    pct_from_high = price / high_52w - 1.0 if high_52w else 0.0
    pct_above_low = price / low_52w - 1.0 if low_52w else 0.0

    rs_outperformance = blended_outperformance(
        close, benchmark_close, config.rs_lookbacks, config.rs_weights
    )
    rs_line_new_high = rs_line_at_high(
        close, benchmark_close, config.rs_line_window, tolerance=0.02
    )

    pivot = _prior_extreme(high, config.breakout_window, kind='high', fallback=price)
    recent_high = _prior_extreme(high, config.recent_high_window, kind='high', fallback=price)
    pivot_low = float(rolling_low(low, config.recent_high_window).iloc[-1])
    base_high = float(rolling_high(high, config.base_window).iloc[-1])
    base_low = float(rolling_low(low, config.base_window).iloc[-1])
    base_depth = (base_high - base_low) / base_high if base_high else 0.0

    atr_value = _last(atr(high, low, close, config.atr_period), 0.0)
    short_atr = _last(atr(high, low, close, config.short_atr_period), atr_value)
    long_atr = _last(atr(high, low, close, config.long_atr_period), atr_value)
    contraction_ratio = short_atr / long_atr if long_atr else 1.0
    atr_pct = atr_value / price if price else 0.0

    avg_volume = _last(sma(volume, config.volume_window), float(volume.iloc[-1]))
    rel_volume = float(volume.iloc[-1]) / avg_volume if avg_volume else 0.0
    updown_volume_ratio = _updown_volume_ratio(close, volume, config.updown_window)
    obv_slope = slope_pct(on_balance_volume(close, volume), config.slope_lookback)

    trend_score = _trend_template_score(
        price=price,
        ma_fast=ma_fast,
        ma_mid=ma_mid,
        ma_long=ma_long,
        ma_long_slope=ma_long_slope,
        ma_mid_slope=ma_mid_slope,
        pct_above_low=pct_above_low,
        pct_from_high=pct_from_high,
        rs_outperformance=rs_outperformance,
        config=config,
    )
    stacked = price > ma_fast > ma_mid > ma_long

    return MarketFeatures(
        price=price,
        ma_fast=ma_fast,
        ma_mid=ma_mid,
        ma_long=ma_long,
        ema_trend=ema_trend,
        ma_long_slope=ma_long_slope,
        ma_mid_slope=ma_mid_slope,
        stacked=stacked,
        trend_score=trend_score,
        high_52w=high_52w,
        low_52w=low_52w,
        pct_from_high=pct_from_high,
        pct_above_low=pct_above_low,
        rs_outperformance=rs_outperformance,
        rs_line_new_high=rs_line_new_high,
        pivot=pivot,
        recent_high=recent_high,
        pivot_low=pivot_low,
        base_high=base_high,
        base_low=base_low,
        base_depth=base_depth,
        atr=atr_value,
        atr_pct=atr_pct,
        contraction_ratio=contraction_ratio,
        avg_volume=avg_volume,
        rel_volume=rel_volume,
        updown_volume_ratio=updown_volume_ratio,
        obv_slope=obv_slope,
    )


def _ohlc_series(df: pd.DataFrame, column: str, close: pd.Series) -> pd.Series:
    if column in df.columns:
        return df[column].reindex(close.index).fillna(close)
    return close


def _prior_extreme(series: pd.Series, window: int, *, kind: str, fallback: float) -> float:
    """Highest high / lowest low over ``window`` bars *before* the current one."""
    roll = rolling_high(series, window) if kind == 'high' else rolling_low(series, window)
    prior = roll.shift(1).iloc[-1]
    return float(prior) if pd.notna(prior) else fallback


def _updown_volume_ratio(close: pd.Series, volume: pd.Series, window: int) -> float:
    change = close.diff().tail(window)
    vol = volume.tail(window)
    up_volume = vol[change > 0].sum()
    down_volume = vol[change < 0].sum()
    if down_volume == 0:
        return 2.0 if up_volume > 0 else 1.0
    return float(up_volume / down_volume)


def _trend_template_score(
    *,
    price: float,
    ma_fast: float,
    ma_mid: float,
    ma_long: float,
    ma_long_slope: float,
    ma_mid_slope: float,
    pct_above_low: float,
    pct_from_high: float,
    rs_outperformance: float,
    config: StrategyConfig,
) -> float:
    conditions = (
        price > ma_fast,
        ma_fast > ma_mid,
        ma_mid > ma_long,
        price > ma_long,
        ma_long_slope > 0,
        ma_mid_slope > 0,
        pct_above_low >= config.min_above_low,
        pct_from_high >= -config.max_below_high,
        rs_outperformance > 0,
    )
    return sum(conditions) / len(conditions)


def _last(series: pd.Series, default: float) -> float:
    clean = series.dropna()
    return float(clean.iloc[-1]) if not clean.empty else default
