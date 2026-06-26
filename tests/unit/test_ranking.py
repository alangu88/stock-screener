import pandas as pd

from src.screener.ranking import (
    MarketContext,
    assess_market_context,
    composite_rank,
    confidence_score,
)
from src.screener.setups import AVOID, BREAKOUT, Setup
from src.screener.strategy import StrategyConfig
from src.screener.trade_plan import NO_PLAN, build_trade_plan
from tests.unit._features_factory import make_features

CONFIG = StrategyConfig()


def _setup(setup_type: str) -> Setup:
    return Setup(setup_type, 'reason', (), ())


def test_strong_breakout_scores_high_confidence():
    features = make_features(price=102.0, pivot=100.0, pivot_low=98.0, rel_volume=1.5)
    plan = build_trade_plan(features, _setup(BREAKOUT), CONFIG)
    score = confidence_score(features, _setup(BREAKOUT), plan, CONFIG)
    assert 0 <= score <= 100
    assert score >= 60


def test_avoid_setup_scores_zero():
    features = make_features()
    score = confidence_score(features, _setup(AVOID), NO_PLAN, CONFIG)
    assert score == 0.0


def test_confidence_stays_finite_when_min_reward_risk_is_one():
    # min_reward_risk == 1.0 makes the reward component's denominator zero;
    # the score must stay a finite 0..100 value (no NaN/inf).
    config = StrategyConfig(min_reward_risk=1.0)
    features = make_features(price=102.0, pivot=100.0, pivot_low=98.0, rel_volume=1.5)
    plan = build_trade_plan(features, _setup(BREAKOUT), config)
    score = confidence_score(features, _setup(BREAKOUT), plan, config)
    assert 0.0 <= score <= 100.0


def test_composite_rank_scales_with_market_context():
    risk_on = composite_rank(80.0, MarketContext(1.0, 'Risk-On'))
    risk_off = composite_rank(80.0, MarketContext(0.0, 'Risk-Off'))
    assert risk_on == 80.0
    assert risk_off == 56.0
    assert risk_on > risk_off


def test_market_context_detects_uptrend():
    rising = pd.Series(range(100, 400), dtype=float)
    context = assess_market_context(rising, CONFIG)
    assert context.label == 'Risk-On'
    assert context.score >= 0.75


def test_market_context_detects_downtrend():
    falling = pd.Series(range(400, 100, -1), dtype=float)
    context = assess_market_context(falling, CONFIG)
    assert context.label == 'Risk-Off'
    assert context.score < 0.4
