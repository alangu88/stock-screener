from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


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
    page_size_default: int = 25
    core_allocation: float = 0.70
    core_score_threshold: float = 0.60
    max_position_weight: float = 0.10


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
        ('page_size_default', 'PAGE_SIZE_DEFAULT', int),
        ('core_allocation', 'CORE_ALLOCATION', float),
        ('core_score_threshold', 'CORE_SCORE_THRESHOLD', float),
        ('max_position_weight', 'MAX_POSITION_WEIGHT', float),
    )

    values = {}
    for attr, suffix, cast in overrides:
        raw = os.getenv(f'SCREENER_{suffix}')
        values[attr] = cast(raw) if raw is not None else getattr(defaults, attr)
    return Settings(**values)

