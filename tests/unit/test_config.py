from __future__ import annotations

import dataclasses

import pytest

from src.config import Settings, load_settings
from src.utils.errors import ConfigError


def test_defaults_are_valid() -> None:
    settings = Settings()
    assert settings.cache_ttl_hours == 24
    assert settings.core_allocation_min <= settings.core_allocation_max


@pytest.mark.parametrize(
    'field, value',
    [
        ('cache_ttl_hours', 0),
        ('max_retries', 0),
        ('atr_stop_multiplier', 0.0),
        ('rsi_period', -1),
        ('rec_min_reward_risk', 0.0),
        ('fundamentals_ttl_hours', 0),
    ],
)
def test_non_positive_fields_rejected(field: str, value: object) -> None:
    with pytest.raises(ConfigError):
        dataclasses.replace(Settings(), **{field: value})


@pytest.mark.parametrize('field', ['backoff_seconds', 'min_avg_volume', 'risk_per_trade'])
def test_negative_fields_rejected(field: str) -> None:
    with pytest.raises(ConfigError):
        dataclasses.replace(Settings(), **{field: -1})


@pytest.mark.parametrize('value', [-0.01, 1.01])
def test_fraction_bounds_enforced(value: float) -> None:
    with pytest.raises(ConfigError):
        dataclasses.replace(Settings(), core_allocation=value)


def test_core_allocation_band_must_be_ordered() -> None:
    with pytest.raises(ConfigError):
        dataclasses.replace(Settings(), core_allocation_min=0.8, core_allocation_max=0.6)


@pytest.mark.parametrize('value', [-1.0, 101.0])
def test_confidence_bounds_enforced(value: float) -> None:
    with pytest.raises(ConfigError):
        dataclasses.replace(Settings(), rec_min_confidence=value)


@pytest.mark.parametrize('value', [-1.0, 101.0])
def test_watchlist_auto_confidence_bounds_enforced(value: float) -> None:
    with pytest.raises(ConfigError):
        dataclasses.replace(Settings(), watchlist_auto_confidence=value)


def test_load_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SCREENER_CACHE_TTL_HOURS', '12')
    monkeypatch.setenv('SCREENER_RISK_PER_TRADE', '0.02')
    settings = load_settings()
    assert settings.cache_ttl_hours == 12
    assert settings.risk_per_trade == 0.02


def test_strategy_confidence_weights_must_sum_to_one() -> None:
    import dataclasses as dc

    from src.screener.strategy import StrategyConfig

    StrategyConfig()  # defaults sum to 1.0
    with pytest.raises(ValueError):
        dc.replace(StrategyConfig(), weight_trend=0.99)


def test_load_settings_rejects_invalid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SCREENER_MAX_RETRIES', '0')
    with pytest.raises(ConfigError):
        load_settings()
