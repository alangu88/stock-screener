"""Centralized strategy configuration.

Every threshold used by feature engineering, setup detection, trade planning,
and ranking lives here so the methodology is tunable in one place and the
calculations stay deterministic. The live model is volume-primary (MA trend +
Donchian channel + volume confirmation); the thresholds below feed both that
model and the shared feature layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import SIGNAL_MODEL_MA_DC_VOLUME_REGIME, Settings


@dataclass(frozen=True)
class StrategyConfig:
    # --- Signal-model feature flag ------------------------------------------
    signal_model: str = SIGNAL_MODEL_MA_DC_VOLUME_REGIME

    # --- Moving-average trend structure (Weinstein stage / Minervini template) -
    ma_fast: int = 50
    ma_mid: int = 150
    ma_long: int = 200
    ema_trend: int = 21
    slope_lookback: int = 20

    # --- 52-week positioning (leadership filter) ----------------------------
    high_low_window: int = 252
    min_above_low: float = 0.25  # >= 25% above the 1-year low
    max_below_high: float = 0.25  # within 25% of the 1-year high

    # --- Relative strength (CAN SLIM RS rating idea) ------------------------
    rs_lookbacks: tuple[int, ...] = (21, 63, 126)
    rs_weights: tuple[float, ...] = (0.5, 0.3, 0.2)

    # --- Breakout / base structure (Darvas box, O'Neil pivot) ---------------
    breakout_window: int = 50
    base_window: int = 30
    extended_threshold: float = 0.05  # > 5% past the pivot is chasing
    recent_high_window: int = 10  # short-term high/low window for pivot & stop refs

    # --- Pullback (trend continuation) --------------------------------------
    pullback_tolerance: float = 0.04  # within 4% of the rising MA

    # --- Volatility (short/long ATR) ----------------------------------------
    atr_period: int = 14
    short_atr_period: int = 10
    long_atr_period: int = 50

    # --- Volume / accumulation (Wyckoff effort-vs-result) -------------------
    volume_window: int = 50
    breakout_volume_mult: float = 1.4  # breakout day vs average
    updown_window: int = 50

    # --- Risk: stops & targets ----------------------------------------------
    atr_stop_mult: float = 2.0
    stop_buffer_atr: float = 0.25  # cushion below structure to avoid noise
    # Asymmetric-payoff floor. Set to 1.5 (not 2.0) so structurally sound setups
    # with R/R ~1.8 are not silently filtered out, while still demanding
    # favorable asymmetry.
    min_reward_risk: float = 1.5
    max_risk_pct: float = 0.12  # capital-preservation cap on per-trade risk

    @classmethod
    def from_settings(cls, settings: Settings) -> StrategyConfig:
        # Only data/liquidity windows track Settings; the remaining thresholds are
        # fixed methodology (tune them here, not via env) to keep backtests stable.
        return cls(
            signal_model=settings.signal_model,
            ma_fast=settings.sma_short_window,
            ma_long=settings.sma_long_window,
            ema_trend=settings.ema_window,
            volume_window=settings.volume_window,
            atr_period=settings.atr_period,
            atr_stop_mult=settings.atr_stop_multiplier,
        )
