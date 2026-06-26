"""Centralized strategy configuration.

Every threshold used by feature engineering, setup detection, trade planning,
and ranking lives here so the methodology is tunable in one place and the
calculations stay deterministic. Values are derived from principles common to
trend-following and leadership-momentum playbooks (O'Neil, Minervini,
Weinstein, Wyckoff, Darvas, Turtle trend following) rather than copied from any
single arbitrary rulebook.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import Settings


@dataclass(frozen=True)
class StrategyConfig:
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
    rs_line_window: int = 126

    # --- Breakout / base structure (Darvas box, O'Neil pivot) ---------------
    breakout_window: int = 50
    base_window: int = 30
    pivot_proximity: float = 0.06  # coiled within 6% under the pivot
    extended_threshold: float = 0.05  # > 5% past the pivot is chasing
    recent_high_window: int = 10  # short-term trigger for reversals

    # --- Pullback (trend continuation) --------------------------------------
    pullback_tolerance: float = 0.04  # within 4% of the rising MA

    # --- Volatility contraction (VCP) ---------------------------------------
    atr_period: int = 14
    short_atr_period: int = 10
    long_atr_period: int = 50
    contraction_ratio: float = 0.85  # short ATR / long ATR below this = drying up

    # --- Volume / accumulation (Wyckoff effort-vs-result) -------------------
    volume_window: int = 50
    breakout_volume_mult: float = 1.4  # breakout day vs average
    updown_window: int = 50

    # --- Risk: stops & targets ----------------------------------------------
    atr_stop_mult: float = 2.0
    stop_buffer_atr: float = 0.25  # cushion below structure to avoid noise
    # Asymmetric-payoff floor. Lowered from 2.0 to 1.5 so volatility contractions
    # (structural R/R ~1.8, the strongest realized edge in backtests) are no
    # longer silently filtered out, while still demanding favorable asymmetry.
    min_reward_risk: float = 1.5
    max_risk_pct: float = 0.12  # capital-preservation cap on per-trade risk

    # --- Confidence weights (must sum to 1) ---------------------------------
    weight_trend: float = 0.22
    weight_rs: float = 0.24
    weight_setup: float = 0.16
    weight_volume: float = 0.14
    weight_contraction: float = 0.12
    weight_reward: float = 0.12

    # --- Screening gates -----------------------------------------------------
    min_confidence: float = 45.0
    min_avg_volume: int = 500_000

    @classmethod
    def from_settings(cls, settings: Settings) -> StrategyConfig:
        return cls(
            ma_fast=settings.sma_short_window,
            ma_long=settings.sma_long_window,
            ema_trend=settings.ema_window,
            volume_window=settings.volume_window,
            atr_period=settings.atr_period,
            atr_stop_mult=settings.atr_stop_multiplier,
            min_avg_volume=settings.min_avg_volume,
        )

    @property
    def confidence_weights(self) -> dict[str, float]:
        return {
            'trend': self.weight_trend,
            'rs': self.weight_rs,
            'setup': self.weight_setup,
            'volume': self.weight_volume,
            'contraction': self.weight_contraction,
            'reward': self.weight_reward,
        }
