from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.utils.errors import ConfigError

SIGNAL_MODEL_MA_DC_VOLUME = 'ma_dc_volume'
SIGNAL_MODEL_MA_DC_VOLUME_REGIME = 'ma_dc_volume_regime'
SUPPORTED_SIGNAL_MODELS = {
    SIGNAL_MODEL_MA_DC_VOLUME,
    SIGNAL_MODEL_MA_DC_VOLUME_REGIME,
}


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

    # Production signal model: the regime-aware volume model (MA + Donchian +
    # volume, with risk-off breakouts suppressed). `ma_dc_volume` (no regime
    # rule) remains selectable via SCREENER_SIGNAL_MODEL.
    signal_model: str = SIGNAL_MODEL_MA_DC_VOLUME_REGIME

    # Screening recommendation gates
    rec_min_confidence: float = 80.0  # only surface setups scoring at least this (0-100)
    rec_min_reward_risk: float = 2.5  # require at least this structural reward:risk
    require_regime_for_adds: bool = True  # suppress recommendations while SPY is risk-off (below its long SMA)

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
            'rec_min_reward_risk': self.rec_min_reward_risk,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ConfigError(f'{name} must be > 0, got {value!r}')

        non_negative = {
            'backoff_seconds': self.backoff_seconds,
            'request_delay_seconds': self.request_delay_seconds,
            'min_avg_volume': self.min_avg_volume,
        }
        for name, value in non_negative.items():
            if value < 0:
                raise ConfigError(f'{name} must be >= 0, got {value!r}')

        if not 0.0 <= self.rec_min_confidence <= 100.0:
            raise ConfigError(
                f'rec_min_confidence must be within [0, 100], got {self.rec_min_confidence!r}'
            )

        if self.signal_model not in SUPPORTED_SIGNAL_MODELS:
            allowed = ', '.join(sorted(SUPPORTED_SIGNAL_MODELS))
            raise ConfigError(
                f'signal_model must be one of {{{allowed}}}, got {self.signal_model!r}'
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
        ('signal_model', 'SIGNAL_MODEL', str),
        ('rec_min_confidence', 'REC_MIN_CONFIDENCE', float),
        ('rec_min_reward_risk', 'REC_MIN_REWARD_RISK', float),
        ('require_regime_for_adds', 'REQUIRE_REGIME_FOR_ADDS', _as_bool),
    )

    values = {}
    for attr, suffix, cast in overrides:
        env_var = f'SCREENER_{suffix}'
        raw = os.getenv(env_var)
        if raw is None:
            values[attr] = getattr(defaults, attr)
            continue
        try:
            values[attr] = cast(raw)
        except (ValueError, TypeError) as exc:
            raise ConfigError(f'{env_var}={raw!r} is not a valid {cast.__name__}') from exc
    return Settings(**values)

