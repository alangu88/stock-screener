from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.utils.errors import ConfigError


def _as_bool(raw: str) -> bool:
    """Parse a ``SCREENER_*`` flag; truthy for 1/true/yes/on (case-insensitive)."""
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


@dataclass(frozen=True)
class Settings:
    # Data fetching and caching
    cache_dir: Path = Path('.cache')
    cache_ttl_hours: int = 24
    max_retries: int = 4
    backoff_seconds: float = 1.0
    request_delay_seconds: float = 0.25
    fundamentals_max_workers: int = 8
    fundamentals_ttl_hours: int = 24  # slow-moving metadata; kept long so hourly price refreshes stay cheap

    # Indicator windows (also drive the StrategyConfig defaults)
    min_avg_volume: int = 500_000
    rsi_period: int = 14
    sma_short_window: int = 50
    sma_long_window: int = 200
    ema_window: int = 20
    volume_window: int = 50
    atr_period: int = 14
    atr_stop_multiplier: float = 2.0

    # UI and portfolio construction
    core_allocation: float = 0.70
    core_score_threshold: float = 0.60
    max_position_weight: float = 0.10

    # Risk-based position sizing and add recommendations
    risk_per_trade: float = 0.01
    conviction_risk_max: float = 0.02  # hard cap when scaling risk by confidence
    max_portfolio_risk: float = 0.08  # cap on aggregate open risk before new adds shrink
    core_allocation_min: float = 0.60
    core_allocation_max: float = 0.70
    max_individual_stocks: int = 10
    rec_min_confidence: float = 80.0
    rec_min_reward_risk: float = 2.5
    watchlist_auto_confidence: float = 80.0  # adds at/above this confidence auto-join watchlist.txt
    suggested_add_fraction: float = 0.5  # starter tranche as a fraction of the max add (scale-in)
    suggested_add_trigger_r: float = 1.0  # add the remainder once the trade is +this many R
    require_regime_for_adds: bool = True  # pause new adds while SPY is below its long SMA (risk-off)

    # Swing-trading management for satellites (on by default; cores unaffected)
    swing_mode: bool = True
    swing_time_stop_bars: int = 20  # cut dead money if no progress within N bars
    swing_extended_atr: float = 0.10  # > this above EMA20 -> extended, scale partial
    scaleout_alert_pct: float = 0.03  # flag holdings within this % below a scale-out level
    earnings_blackout_days: int = 7  # flag holdings/adds within N days of earnings
    dividend_lookback_days: int = 7  # first-run window for the income-to-reconcile digest

    # Present-state Chandelier trailing stop for satellites (cost-basis anchored)
    trail_atr_mult: float = 3.0  # trail at highest-high - this * ATR (3.0 = best-backtested)
    trail_lookback_bars: int = 22  # highest-high window for the trail (present-state, no entry date)
    trail_breakeven_r: float = 1.0  # lock the trail at cost once up this many trail-widths (R)

    def __post_init__(self) -> None:
        positive = {
            'cache_ttl_hours': self.cache_ttl_hours,
            'max_retries': self.max_retries,
            'fundamentals_max_workers': self.fundamentals_max_workers,
            'fundamentals_ttl_hours': self.fundamentals_ttl_hours,
            'rsi_period': self.rsi_period,
            'sma_short_window': self.sma_short_window,
            'sma_long_window': self.sma_long_window,
            'ema_window': self.ema_window,
            'volume_window': self.volume_window,
            'atr_period': self.atr_period,
            'atr_stop_multiplier': self.atr_stop_multiplier,
            'max_position_weight': self.max_position_weight,
            'max_individual_stocks': self.max_individual_stocks,
            'rec_min_reward_risk': self.rec_min_reward_risk,
            'swing_time_stop_bars': self.swing_time_stop_bars,
            'earnings_blackout_days': self.earnings_blackout_days,
            'dividend_lookback_days': self.dividend_lookback_days,
            'suggested_add_fraction': self.suggested_add_fraction,
            'suggested_add_trigger_r': self.suggested_add_trigger_r,
            'trail_atr_mult': self.trail_atr_mult,
            'trail_lookback_bars': self.trail_lookback_bars,
            'trail_breakeven_r': self.trail_breakeven_r,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ConfigError(f'{name} must be > 0, got {value!r}')

        non_negative = {
            'backoff_seconds': self.backoff_seconds,
            'request_delay_seconds': self.request_delay_seconds,
            'min_avg_volume': self.min_avg_volume,
            'risk_per_trade': self.risk_per_trade,
            'swing_extended_atr': self.swing_extended_atr,
            'scaleout_alert_pct': self.scaleout_alert_pct,
        }
        for name, value in non_negative.items():
            if value < 0:
                raise ConfigError(f'{name} must be >= 0, got {value!r}')

        fractions = {
            'core_allocation': self.core_allocation,
            'core_score_threshold': self.core_score_threshold,
            'max_position_weight': self.max_position_weight,
            'risk_per_trade': self.risk_per_trade,
            'conviction_risk_max': self.conviction_risk_max,
            'max_portfolio_risk': self.max_portfolio_risk,
            'core_allocation_min': self.core_allocation_min,
            'core_allocation_max': self.core_allocation_max,
            'suggested_add_fraction': self.suggested_add_fraction,
        }
        for name, value in fractions.items():
            if not 0.0 <= value <= 1.0:
                raise ConfigError(f'{name} must be within [0, 1], got {value!r}')

        if self.core_allocation_min > self.core_allocation_max:
            raise ConfigError(
                'core_allocation_min must be <= core_allocation_max, got '
                f'{self.core_allocation_min!r} > {self.core_allocation_max!r}'
            )

        if not 0.0 <= self.rec_min_confidence <= 100.0:
            raise ConfigError(
                f'rec_min_confidence must be within [0, 100], got {self.rec_min_confidence!r}'
            )

        if not 0.0 <= self.watchlist_auto_confidence <= 100.0:
            raise ConfigError(
                'watchlist_auto_confidence must be within [0, 100], got '
                f'{self.watchlist_auto_confidence!r}'
            )


def load_settings() -> Settings:
    """Build :class:`Settings`, overriding defaults from ``SCREENER_*`` env vars."""
    defaults = Settings()
    # (attribute, SCREENER_* env suffix, cast)
    overrides: tuple[tuple[str, str, Callable[[str], object]], ...] = (
        ('cache_dir', 'CACHE_DIR', Path),
        ('cache_ttl_hours', 'CACHE_TTL_HOURS', int),
        ('max_retries', 'MAX_RETRIES', int),
        ('backoff_seconds', 'BACKOFF_SECONDS', float),
        ('request_delay_seconds', 'REQUEST_DELAY_SECONDS', float),
        ('fundamentals_max_workers', 'FUNDAMENTALS_MAX_WORKERS', int),
        ('fundamentals_ttl_hours', 'FUNDAMENTALS_TTL_HOURS', int),
        ('min_avg_volume', 'MIN_AVG_VOLUME', int),
        ('rsi_period', 'RSI_PERIOD', int),
        ('sma_short_window', 'SMA_SHORT_WINDOW', int),
        ('sma_long_window', 'SMA_LONG_WINDOW', int),
        ('ema_window', 'EMA_WINDOW', int),
        ('volume_window', 'VOLUME_WINDOW', int),
        ('atr_period', 'ATR_PERIOD', int),
        ('atr_stop_multiplier', 'ATR_STOP_MULTIPLIER', float),
        ('core_allocation', 'CORE_ALLOCATION', float),
        ('core_score_threshold', 'CORE_SCORE_THRESHOLD', float),
        ('max_position_weight', 'MAX_POSITION_WEIGHT', float),
        ('risk_per_trade', 'RISK_PER_TRADE', float),
        ('conviction_risk_max', 'CONVICTION_RISK_MAX', float),
        ('max_portfolio_risk', 'MAX_PORTFOLIO_RISK', float),
        ('core_allocation_min', 'CORE_ALLOCATION_MIN', float),
        ('core_allocation_max', 'CORE_ALLOCATION_MAX', float),
        ('max_individual_stocks', 'MAX_INDIVIDUAL_STOCKS', int),
        ('rec_min_confidence', 'REC_MIN_CONFIDENCE', float),
        ('rec_min_reward_risk', 'REC_MIN_REWARD_RISK', float),
        ('watchlist_auto_confidence', 'WATCHLIST_AUTO_CONFIDENCE', float),
        ('suggested_add_fraction', 'SUGGESTED_ADD_FRACTION', float),
        ('suggested_add_trigger_r', 'SUGGESTED_ADD_TRIGGER_R', float),
        ('require_regime_for_adds', 'REQUIRE_REGIME_FOR_ADDS', _as_bool),
        ('swing_mode', 'SWING_MODE', _as_bool),
        ('swing_time_stop_bars', 'SWING_TIME_STOP_BARS', int),
        ('swing_extended_atr', 'SWING_EXTENDED_ATR', float),
        ('scaleout_alert_pct', 'SCALEOUT_ALERT_PCT', float),
        ('earnings_blackout_days', 'EARNINGS_BLACKOUT_DAYS', int),
        ('dividend_lookback_days', 'DIVIDEND_LOOKBACK_DAYS', int),
        ('trail_atr_mult', 'TRAIL_ATR_MULT', float),
        ('trail_lookback_bars', 'TRAIL_LOOKBACK_BARS', int),
        ('trail_breakeven_r', 'TRAIL_BREAKEVEN_R', float),
    )

    values = {}
    for attr, suffix, cast in overrides:
        raw = os.getenv(f'SCREENER_{suffix}')
        values[attr] = cast(raw) if raw is not None else getattr(defaults, attr)
    return Settings(**values)

