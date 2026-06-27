from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.utils.errors import ConfigError


@dataclass(frozen=True)
class Settings:
    # Data fetching and caching
    cache_dir: Path = Path('.cache')
    cache_ttl_hours: int = 24
    max_retries: int = 4
    backoff_seconds: float = 1.0
    request_delay_seconds: float = 0.25
    fundamentals_max_workers: int = 8

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
    core_allocation_min: float = 0.60
    core_allocation_max: float = 0.70
    max_individual_stocks: int = 10
    rec_min_confidence: float = 85.0
    rec_min_reward_risk: float = 2.5

    def __post_init__(self) -> None:
        positive = {
            'cache_ttl_hours': self.cache_ttl_hours,
            'max_retries': self.max_retries,
            'fundamentals_max_workers': self.fundamentals_max_workers,
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
        }
        for name, value in positive.items():
            if value <= 0:
                raise ConfigError(f'{name} must be > 0, got {value!r}')

        non_negative = {
            'backoff_seconds': self.backoff_seconds,
            'request_delay_seconds': self.request_delay_seconds,
            'min_avg_volume': self.min_avg_volume,
            'risk_per_trade': self.risk_per_trade,
        }
        for name, value in non_negative.items():
            if value < 0:
                raise ConfigError(f'{name} must be >= 0, got {value!r}')

        fractions = {
            'core_allocation': self.core_allocation,
            'core_score_threshold': self.core_score_threshold,
            'max_position_weight': self.max_position_weight,
            'risk_per_trade': self.risk_per_trade,
            'core_allocation_min': self.core_allocation_min,
            'core_allocation_max': self.core_allocation_max,
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
        ('core_allocation_min', 'CORE_ALLOCATION_MIN', float),
        ('core_allocation_max', 'CORE_ALLOCATION_MAX', float),
        ('max_individual_stocks', 'MAX_INDIVIDUAL_STOCKS', int),
        ('rec_min_confidence', 'REC_MIN_CONFIDENCE', float),
        ('rec_min_reward_risk', 'REC_MIN_REWARD_RISK', float),
    )

    values = {}
    for attr, suffix, cast in overrides:
        raw = os.getenv(f'SCREENER_{suffix}')
        values[attr] = cast(raw) if raw is not None else getattr(defaults, attr)
    return Settings(**values)

