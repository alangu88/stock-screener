from src.screener.setups import (
    AVOID,
    BREAKOUT,
    PULLBACK,
    detect_setup,
)
from src.screener.strategy import StrategyConfig
from tests.unit._features_factory import make_features

CONFIG = StrategyConfig()
VOLUME_MODEL = StrategyConfig(signal_model='ma_dc_volume')


def test_confirmed_breakout_on_volume():
    features = make_features(price=102.0, pivot=100.0, rel_volume=1.5)
    setup = detect_setup(features, CONFIG)
    assert setup.setup_type == BREAKOUT
    assert setup.factors and setup.risks


def test_pullback_to_rising_support():
    features = make_features(
        price=102.0, ema_trend=100.0, ma_fast=100.0, pivot=110.0,
        contraction_ratio=1.0, rel_volume=1.0,
    )
    setup = detect_setup(features, CONFIG)
    assert setup.setup_type == PULLBACK


def test_below_primary_trend_is_avoided():
    # Formerly an "early reversal" setup; removed because backtesting showed a
    # negative expectancy. Such counter-trend conditions are now non-actionable.
    features = make_features(
        price=80.0, ma_fast=78.0, ma_long=90.0, trend_score=0.5,
        pct_above_low=0.30, rs_outperformance=-0.05, pivot=100.0,
        updown_volume_ratio=1.5, obv_slope=0.05,
    )
    setup = detect_setup(features, CONFIG)
    assert setup.setup_type == AVOID


def test_extended_price_is_avoided():
    features = make_features(
        price=110.0, pivot=100.0, ema_trend=100.0, ma_fast=100.0,
        contraction_ratio=1.0, rel_volume=1.0,
    )
    setup = detect_setup(features, CONFIG)
    assert setup.setup_type == AVOID
    assert 'Extended' in setup.reason


def test_volume_breakout_requires_volume_surge_and_accumulation():
    # MA/Donchian aligned + volume surge + accumulation -> breakout.
    confirmed = make_features(
        price=101.0, pivot=100.0, ma_fast=95.0, ma_long=85.0, ma_long_slope=0.05,
        rel_volume=1.6, updown_volume_ratio=1.4, obv_slope=0.05,
    )
    setup = detect_setup(confirmed, VOLUME_MODEL)
    assert setup.setup_type == BREAKOUT

    # Same chart but volume does not confirm -> Avoid (volume is primary).
    no_volume = make_features(
        price=101.0, pivot=100.0, ma_fast=95.0, ma_long=85.0, ma_long_slope=0.05,
        rel_volume=1.0, updown_volume_ratio=1.4, obv_slope=0.05,
    )
    assert detect_setup(no_volume, VOLUME_MODEL).setup_type == AVOID


def test_volume_model_avoids_when_ma_trend_not_intact():
    # Volume surge but price below the long MA -> no trend, no trade.
    features = make_features(
        price=84.0, pivot=100.0, ma_fast=95.0, ma_long=85.0, ma_long_slope=0.05,
        rel_volume=1.8, updown_volume_ratio=1.5, obv_slope=0.05,
    )
    assert detect_setup(features, VOLUME_MODEL).setup_type == AVOID


def test_volume_pullback_needs_quiet_accumulation_volume():
    features = make_features(
        price=102.0, pivot=110.0, ema_trend=100.0, ma_fast=100.0, ma_long=85.0,
        ma_long_slope=0.05, rel_volume=0.9, updown_volume_ratio=1.3, obv_slope=0.04,
    )
    assert detect_setup(features, VOLUME_MODEL).setup_type == PULLBACK
