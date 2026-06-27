import pytest

from src.screener.setups import AVOID, BREAKOUT, CONTRACTION, Setup
from src.screener.strategy import StrategyConfig
from src.screener.trade_plan import NO_PLAN, build_trade_plan, management_plan
from tests.unit._features_factory import make_features

CONFIG = StrategyConfig()


def _setup(setup_type: str) -> Setup:
    return Setup(setup_type, 'reason', (), ())


def test_breakout_plan_is_asymmetric_and_immediate():
    features = make_features(
        price=102.0, pivot=100.0, pivot_low=98.0, base_high=104.0, base_low=90.0, atr=1.0
    )
    plan = build_trade_plan(features, _setup(BREAKOUT), CONFIG)
    assert plan.immediate_entry is True
    assert plan.entry == 102.0
    # Stop sits a quarter-ATR below the tight contraction low, not the deep base.
    assert plan.stop == pytest.approx(98.0 - CONFIG.stop_buffer_atr * 1.0)
    # Target projects the full structural measured move (base height).
    assert plan.target == pytest.approx(102.0 + (104.0 - 90.0))
    assert plan.stop < plan.entry < plan.target
    assert plan.reward_risk >= CONFIG.min_reward_risk


def test_contraction_entry_is_a_buy_stop_at_the_pivot():
    features = make_features(
        price=96.0, pivot=100.0, pivot_low=95.0, base_high=104.0, base_low=92.0, atr=1.0
    )
    plan = build_trade_plan(features, _setup(CONTRACTION), CONFIG)
    assert plan.immediate_entry is False
    assert plan.entry == 100.0  # does not chase the current price
    assert plan.entry > features.price


def test_risk_is_capped_at_max_risk_pct():
    # A very deep structure low would imply huge risk; the cap tightens the stop.
    # Uses a contraction so the breakout ATR tightening does not mask the cap.
    features = make_features(
        price=100.0, pivot=100.0, pivot_low=50.0, base_high=120.0, base_low=40.0, atr=1.0
    )
    plan = build_trade_plan(features, _setup(CONTRACTION), CONFIG)
    assert plan.stop == 100.0 * (1 - CONFIG.max_risk_pct)


def test_avoid_setup_has_no_plan():
    features = make_features()
    plan = build_trade_plan(features, _setup(AVOID), CONFIG)
    assert plan is NO_PLAN
    assert plan.entry is None


def test_management_plan_is_always_valid_and_asymmetric():
    # Healthy name: stop rides the nearest support below price, target is upside.
    features = make_features(price=100.0)
    plan = management_plan(features, CONFIG)
    assert plan.entry == 100.0
    assert plan.immediate_entry is False
    assert plan.stop < plan.entry < plan.target
    assert plan.reward_risk is not None and plan.reward_risk > 0


def test_management_plan_caps_risk_when_price_below_all_support():
    # Broken downtrend: price under every MA/structure -> stop is the risk cap.
    features = make_features(
        price=50.0, ma_fast=95.0, ma_long=85.0, base_low=70.0, pivot_low=72.0
    )
    plan = management_plan(features, CONFIG)
    assert plan.stop == pytest.approx(50.0 * (1 - CONFIG.max_risk_pct))
    assert plan.stop < plan.entry < plan.target
