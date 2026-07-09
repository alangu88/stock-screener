from __future__ import annotations

import dataclasses

import pytest

from src.config import (
    SIGNAL_MODEL_MA_DC_VOLUME,
    SIGNAL_MODEL_MA_DC_VOLUME_REGIME,
    Settings,
    load_settings,
)
from src.utils.errors import ConfigError


def test_defaults_are_valid() -> None:
    settings = Settings()
    assert settings.cache_ttl_hours == 24
    assert settings.signal_model == SIGNAL_MODEL_MA_DC_VOLUME_REGIME


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


@pytest.mark.parametrize('field', ['backoff_seconds', 'min_avg_volume'])
def test_negative_fields_rejected(field: str) -> None:
    with pytest.raises(ConfigError):
        dataclasses.replace(Settings(), **{field: -1})


@pytest.mark.parametrize('value', [-1.0, 101.0])
def test_confidence_bounds_enforced(value: float) -> None:
    with pytest.raises(ConfigError):
        dataclasses.replace(Settings(), rec_min_confidence=value)


def test_load_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SCREENER_CACHE_TTL_HOURS', '12')
    monkeypatch.setenv('SCREENER_REC_MIN_CONFIDENCE', '70')
    settings = load_settings()
    assert settings.cache_ttl_hours == 12
    assert settings.rec_min_confidence == 70.0


def test_require_regime_for_adds_defaults_on_and_reads_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert load_settings().require_regime_for_adds is True
    monkeypatch.setenv('SCREENER_REQUIRE_REGIME_FOR_ADDS', 'false')
    assert load_settings().require_regime_for_adds is False


def test_load_settings_rejects_invalid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SCREENER_MAX_RETRIES', '0')
    with pytest.raises(ConfigError):
        load_settings()


def test_signal_model_defaults_to_regime_and_accepts_supported_values() -> None:
    assert Settings().signal_model == SIGNAL_MODEL_MA_DC_VOLUME_REGIME
    assert dataclasses.replace(Settings(), signal_model=SIGNAL_MODEL_MA_DC_VOLUME).signal_model == (
        SIGNAL_MODEL_MA_DC_VOLUME
    )


def test_signal_model_rejects_unknown_value() -> None:
    with pytest.raises(ConfigError):
        dataclasses.replace(Settings(), signal_model='unknown-model')


def test_load_settings_reads_signal_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SCREENER_SIGNAL_MODEL', SIGNAL_MODEL_MA_DC_VOLUME)
    loaded = load_settings()
    assert loaded.signal_model == SIGNAL_MODEL_MA_DC_VOLUME


def test_strategy_config_inherits_signal_model_from_settings() -> None:
    from src.screener.strategy import StrategyConfig

    s = dataclasses.replace(Settings(), signal_model=SIGNAL_MODEL_MA_DC_VOLUME)
    cfg = StrategyConfig.from_settings(s)
    assert cfg.signal_model == SIGNAL_MODEL_MA_DC_VOLUME
