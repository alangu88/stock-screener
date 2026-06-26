"""Unit tests for Core/Satellite portfolio construction."""

from __future__ import annotations

import pandas as pd
import pytest

from src.screener.portfolio import (
    CORE,
    PORTFOLIO_COLUMNS,
    SATELLITE,
    PortfolioConfig,
    assign_portfolio,
    core_score,
    sleeve_summary,
)
from src.screener.setups import BREAKOUT, CONTRACTION, PULLBACK

CONFIG = PortfolioConfig()


def _row(ticker: str, setup: str, confidence: float, risk: float, market_cap, trend: float, rr: float = 2.0) -> dict:
    return {
        'Ticker': ticker,
        'Setup': setup,
        'Confidence': confidence,
        'Risk %': risk,
        'Reward %': risk * rr,
        'R/R': rr,
        'Market Cap': market_cap,
        'Trend Score': trend,
    }


def test_core_score_orders_setups_for_equal_inputs():
    pullback = core_score(PULLBACK, 80.0, 1e11, 0.8, CONFIG)
    contraction = core_score(CONTRACTION, 80.0, 1e11, 0.8, CONFIG)
    breakout = core_score(BREAKOUT, 80.0, 1e11, 0.8, CONFIG)
    assert pullback > contraction > breakout


def test_core_score_is_clamped_to_unit_interval():
    high = core_score(PULLBACK, 100.0, 5e12, 1.0, CONFIG)
    low = core_score(BREAKOUT, 0.0, 5e8, 0.0, CONFIG)
    assert 0.0 <= low <= high <= 1.0


def test_missing_market_cap_uses_neutral_value():
    score = core_score(PULLBACK, 80.0, None, 0.8, CONFIG)
    assert 0.0 < score < 1.0


def test_classification_splits_on_threshold():
    df = pd.DataFrame([
        _row('AAA', PULLBACK, 90.0, 0.04, 1e12, 0.95),   # strong leader -> Core
        _row('BBB', BREAKOUT, 50.0, 0.10, 8e8, 0.30),    # tactical -> Satellite
    ])
    out = assign_portfolio(df, CONFIG)
    sleeves = dict(zip(out['Ticker'], out['Sleeve'], strict=True))
    assert sleeves['AAA'] == CORE
    assert sleeves['BBB'] == SATELLITE


def test_position_sizing_fills_sleeve_allocations_when_uncapped():
    # With a non-binding per-name cap, each sleeve deploys its full allocation.
    config = PortfolioConfig(max_position_weight=1.0)
    df = pd.DataFrame([
        _row('AAA', PULLBACK, 90.0, 0.05, 1e12, 0.95),
        _row('CCC', CONTRACTION, 80.0, 0.04, 5e11, 0.85),
        _row('BBB', BREAKOUT, 55.0, 0.10, 8e8, 0.30),
    ])
    out = assign_portfolio(df, config)
    core_weight = out.loc[out['Sleeve'] == CORE, 'Position Size %'].sum()
    sat_weight = out.loc[out['Sleeve'] == SATELLITE, 'Position Size %'].sum()
    assert core_weight == pytest.approx(config.core_allocation, abs=1e-6)
    assert sat_weight == pytest.approx(config.satellite_allocation, abs=1e-6)


def test_per_name_cap_can_leave_sleeve_partly_in_cash():
    # Few names + a tight cap => the sleeve cannot be fully invested.
    df = pd.DataFrame([
        _row('AAA', PULLBACK, 90.0, 0.05, 1e12, 0.95),
        _row('CCC', CONTRACTION, 80.0, 0.04, 5e11, 0.85),
    ])
    out = assign_portfolio(df, PortfolioConfig(max_position_weight=0.10))
    core_weight = out.loc[out['Sleeve'] == CORE, 'Position Size %'].sum()
    assert core_weight == pytest.approx(0.20, abs=1e-6)  # 2 names capped at 10%
    assert (out['Position Size %'] <= 0.10 + 1e-9).all()


def test_no_position_exceeds_max_weight():
    # Many near-identical core names so naive sizing would clear the cap.
    rows = [_row(f'T{i}', PULLBACK, 80.0, 0.05, 1e12, 0.9) for i in range(3)]
    config = PortfolioConfig(max_position_weight=0.25)
    out = assign_portfolio(pd.DataFrame(rows), config)
    assert (out['Position Size %'] <= config.max_position_weight + 1e-9).all()


def test_risk_parity_gives_lower_risk_more_weight():
    df = pd.DataFrame([
        _row('LOWRISK', PULLBACK, 80.0, 0.02, 1e12, 0.9),
        _row('HIGHRISK', PULLBACK, 80.0, 0.08, 1e12, 0.9),
    ])
    out = assign_portfolio(df, PortfolioConfig(max_position_weight=1.0)).set_index('Ticker')
    assert out.loc['LOWRISK', 'Position Size %'] > out.loc['HIGHRISK', 'Position Size %']


def test_risk_contribution_is_weight_times_risk():
    df = pd.DataFrame([_row('AAA', PULLBACK, 80.0, 0.04, 1e12, 0.9)])
    out = assign_portfolio(df, PortfolioConfig(max_position_weight=1.0)).iloc[0]
    assert out['Risk Contribution %'] == pytest.approx(out['Position Size %'] * 0.04, abs=1e-6)


def test_zero_risk_names_are_skipped():
    df = pd.DataFrame([
        _row('GOOD', PULLBACK, 80.0, 0.04, 1e12, 0.9),
        _row('BADRISK', PULLBACK, 80.0, 0.0, 1e12, 0.9),
    ])
    out = assign_portfolio(df, PortfolioConfig(max_position_weight=1.0)).set_index('Ticker')
    assert out.loc['BADRISK', 'Position Size %'] == 0.0
    assert out.loc['GOOD', 'Position Size %'] > 0.0


def test_empty_frame_gets_portfolio_columns():
    out = assign_portfolio(pd.DataFrame(), CONFIG)
    assert out.empty
    for column in PORTFOLIO_COLUMNS:
        assert column in out.columns


def test_sleeve_summary_has_core_satellite_and_total():
    df = pd.DataFrame([
        _row('AAA', PULLBACK, 90.0, 0.05, 1e12, 0.95),
        _row('BBB', BREAKOUT, 55.0, 0.10, 8e8, 0.30),
    ])
    out = assign_portfolio(df, CONFIG)
    summary = sleeve_summary(out)
    assert list(summary['Sleeve']) == [CORE, SATELLITE, 'Total']
    total = summary.loc[summary['Sleeve'] == 'Total'].iloc[0]
    assert total['Positions'] == 2
    assert total['Portfolio Heat %'] == pytest.approx(out['Risk Contribution %'].sum(), abs=1e-6)
