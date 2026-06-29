import pandas as pd

from src.config import Settings
from src.screener.advisor import (
    add_sizing,
    analysis_lookup,
    core_rebalance,
    individual_cap_state,
    is_core,
    open_r_multiple,
    pct_to_stop,
    pct_to_target,
    portfolio_open_risk,
    recommendation_rows,
    rotation_candidates,
    satellite_action,
)
from src.screener.holdings import AllocationStats
from src.screener.sizing import PositionSizing

SETTINGS = Settings()
SWING = Settings(swing_mode=True)


def test_is_core_case_insensitive():
    assert is_core('core')
    assert is_core('Core')
    assert is_core('CORE')
    assert not is_core('satellite')
    assert not is_core(None)


def test_analysis_lookup_maps_by_ticker():
    analysis = pd.DataFrame([
        {'Ticker': 'AAA', 'Entry': 10.0},
        {'Ticker': 'BBB', 'Entry': 20.0},
    ])
    lookup = analysis_lookup(analysis)
    assert set(lookup) == {'AAA', 'BBB'}
    assert lookup['BBB']['Entry'] == 20.0


def test_analysis_lookup_empty():
    assert analysis_lookup(None) == {}
    assert analysis_lookup(pd.DataFrame()) == {}


def test_add_sizing_normal():
    sizing = add_sizing(100_000, SETTINGS, {'Entry': 100.0, 'Stop': 90.0}, current_value=0.0)
    assert isinstance(sizing, PositionSizing)
    assert sizing.shares > 0


def test_add_sizing_guards():
    # Non-positive account value
    assert add_sizing(0, SETTINGS, {'Entry': 100.0, 'Stop': 90.0}, 0.0) is None
    # Missing / NaN levels
    assert add_sizing(100_000, SETTINGS, {'Entry': None, 'Stop': 90.0}, 0.0) is None
    assert add_sizing(100_000, SETTINGS, {'Entry': 100.0, 'Stop': float('nan')}, 0.0) is None
    # Entry <= stop -> sizing returns None
    assert add_sizing(100_000, SETTINGS, {'Entry': 90.0, 'Stop': 100.0}, 0.0) is None


def test_add_sizing_denied_at_portfolio_risk_cap():
    row = {'Entry': 100.0, 'Stop': 90.0}
    assert add_sizing(100_000, SETTINGS, row, 0.0, open_risk_pct=SETTINGS.max_portfolio_risk) is None


def test_add_sizing_trims_to_headroom():
    row = {'Entry': 100.0, 'Stop': 90.0}
    near_cap = SETTINGS.max_portfolio_risk - 0.001  # tiny headroom left
    full = add_sizing(100_000, SETTINGS, row, 0.0)
    trimmed = add_sizing(100_000, SETTINGS, row, 0.0, open_risk_pct=near_cap)
    assert trimmed is not None and full is not None
    assert trimmed.shares < full.shares


def test_portfolio_open_risk_excludes_core():
    monitor = pd.DataFrame([
        {'Ticker': 'AAA', 'Sleeve': 'Satellite', 'Shares': 100, 'Price': 50.0},
        {'Ticker': 'CORE', 'Sleeve': 'Core', 'Shares': 100, 'Price': 50.0},
    ])
    lookup = {'AAA': {'Stop': 45.0}, 'CORE': {'Stop': 40.0}}
    dollars, pct = portfolio_open_risk(monitor, lookup, 100_000)
    assert dollars == 500.0  # 100 * (50 - 45); core ignored
    assert pct == 0.005


def test_satellite_action_stop_breached():
    monitor_row = {'Price': 88.0, '% vs SMA200': 0.05, '% vs EMA20': 0.0}
    analysis_row = {'Stop': 90.0, 'Entry': 100.0}
    assert satellite_action(monitor_row, analysis_row, None, False) == 'Exit \u2014 price below stop'


def test_satellite_action_trend_broke():
    monitor_row = {'Price': 95.0, '% vs SMA200': -0.02, '% vs EMA20': 0.0}
    analysis_row = {'Stop': 90.0, 'Entry': 100.0}
    assert satellite_action(monitor_row, analysis_row, None, False) == 'Trim \u2014 below 200-day trend'


def test_satellite_action_add_near():
    monitor_row = {'Price': 101.0, '% vs SMA200': 0.05, '% vs EMA20': 0.02}
    analysis_row = {'Stop': 90.0, 'Entry': 100.0}
    sizing = PositionSizing(shares=5, dollars=500.0, risk_dollars=50.0, weight=0.05, capped_by=None)
    assert satellite_action(monitor_row, analysis_row, sizing, True) == 'Add near $100.00'


def test_satellite_action_extended():
    monitor_row = {'Price': 120.0, '% vs SMA200': 0.30, '% vs EMA20': 0.15}
    analysis_row = {'Stop': 90.0, 'Entry': 100.0}
    assert satellite_action(monitor_row, analysis_row, None, False) == 'Hold \u2014 extended, await pullback'


def test_satellite_action_hold():
    monitor_row = {'Price': 101.0, '% vs SMA200': 0.05, '% vs EMA20': 0.02}
    analysis_row = {'Stop': 90.0, 'Entry': 100.0}
    assert satellite_action(monitor_row, analysis_row, None, False) == 'Hold \u2014 trend intact'


def test_swing_action_cut_stop():
    monitor_row = {'Price': 88.0, '% vs SMA200': 0.05, '% vs EMA20': 0.0, 'Unreal P&L %': -0.1,
                   'Shares': 30, 'Value': 2640.0}
    analysis_row = {'Stop': 90.0, 'Target': 130.0, 'Entry': 100.0}
    assert satellite_action(monitor_row, analysis_row, None, False, SWING) == (
        'Cut \u2014 stop hit (sell 30 sh \u2248 $2,640)'
    )


def test_swing_action_take_profit_target():
    monitor_row = {'Price': 132.0, '% vs SMA200': 0.30, '% vs EMA20': 0.20, 'Unreal P&L %': 0.3,
                   'Shares': 30, 'Value': 3960.0}
    analysis_row = {'Stop': 90.0, 'Target': 130.0, 'Entry': 100.0}
    assert satellite_action(monitor_row, analysis_row, None, False, SWING) == (
        'Take profit \u2014 sell \u2153 at target (sell 10 sh \u2248 $1,320)'
    )


def test_swing_action_cut_trend():
    monitor_row = {'Price': 95.0, '% vs SMA200': -0.02, '% vs EMA20': 0.0, 'Unreal P&L %': -0.05}
    analysis_row = {'Stop': 90.0, 'Target': 130.0, 'Entry': 100.0}
    assert satellite_action(monitor_row, analysis_row, None, False, SWING) == (
        'Cut \u2014 trend broken below 200-day'
    )


def test_swing_action_scale_extended():
    monitor_row = {'Price': 115.0, '% vs SMA200': 0.30, '% vs EMA20': 0.15, 'Unreal P&L %': 0.15}
    analysis_row = {'Stop': 90.0, 'Target': 200.0, 'Entry': 100.0}
    assert satellite_action(monitor_row, analysis_row, None, False, SWING) == (
        'Take profit \u2014 extended, scale out \u2153'
    )


def test_swing_action_trail():
    monitor_row = {'Price': 105.0, '% vs SMA200': 0.10, '% vs EMA20': 0.03, 'Unreal P&L %': 0.05}
    analysis_row = {'Stop': 90.0, 'Target': 200.0, 'Entry': 100.0}
    assert satellite_action(monitor_row, analysis_row, None, False, SWING) == 'Trail \u2014 let it run'


def test_pct_to_stop_and_target():
    assert pct_to_stop(100.0, 90.0) == 0.10
    assert pct_to_target(100.0, 120.0) == 0.20
    assert pct_to_stop(None, 90.0) is None
    assert pct_to_target(100.0, None) is None


def test_swing_action_breakeven():
    monitor_row = {'Price': 110.0, '% vs SMA200': 0.10, '% vs EMA20': 0.03, 'Unreal P&L %': 0.1}
    analysis_row = {'Stop': 90.0, 'Target': 200.0, 'Entry': 100.0}
    assert satellite_action(monitor_row, analysis_row, None, False, SWING) == (
        'Trail \u2014 stop to breakeven'
    )


def test_swing_action_scale_2r():
    monitor_row = {'Price': 121.0, '% vs SMA200': 0.10, '% vs EMA20': 0.04, 'Unreal P&L %': 0.21}
    analysis_row = {'Stop': 90.0, 'Target': 200.0, 'Entry': 100.0}
    assert satellite_action(monitor_row, analysis_row, None, False, SWING) == (
        'Take profit \u2014 +2R, scale out \u2153'
    )


def test_open_r_multiple():
    assert open_r_multiple(120.0, 100.0, 90.0) == 2.0
    assert open_r_multiple(95.0, 100.0, 90.0) == -0.5
    assert open_r_multiple(120.0, 100.0, 100.0) is None
    assert open_r_multiple(None, 100.0, 90.0) is None



def _monitor(tickers_sleeves):
    return pd.DataFrame(
        [{'Ticker': t, 'Sleeve': s} for t, s in tickers_sleeves]
    )


def test_individual_cap_state_under_cap():
    monitor = _monitor([('AAA', 'satellite'), ('BBB', 'satellite')])
    at_cap, note = individual_cap_state(monitor, set(), SETTINGS)
    assert at_cap is False
    assert note == ''


def test_individual_cap_state_at_cap():
    rows = [(f'T{i}', 'satellite') for i in range(SETTINGS.max_individual_stocks)]
    monitor = _monitor(rows)
    at_cap, note = individual_cap_state(monitor, set(), SETTINGS)
    assert at_cap is True
    assert str(SETTINGS.max_individual_stocks) in note


def test_individual_cap_state_etfs_excluded():
    rows = [(f'T{i}', 'satellite') for i in range(SETTINGS.max_individual_stocks)]
    monitor = _monitor(rows)
    # Treat one as an ETF -> back under the cap
    at_cap, _ = individual_cap_state(monitor, {'T0'}, SETTINGS)
    assert at_cap is False


def test_individual_cap_state_missing_sleeve():
    monitor = pd.DataFrame([{'Ticker': 'AAA'}])
    at_cap, note = individual_cap_state(monitor, set(), SETTINGS)
    assert at_cap is False
    assert note == ''


def test_individual_cap_state_none_monitor():
    at_cap, note = individual_cap_state(None, set(), SETTINGS)
    assert at_cap is False
    assert note == ''


def test_recommendation_rows_types_and_sizing():
    recs = pd.DataFrame([
        {
            'Ticker': 'AAA', 'Company Name': 'Alpha', 'Setup': 'breakout',
            'Confidence': 90, 'R/R': 3.0, 'Entry': 100.0, 'Stop': 90.0,
            'Target': 130.0, 'Rank Score': 80.0,
        },
        {
            'Ticker': 'SPY', 'Company Name': 'S&P ETF', 'Setup': 'pullback',
            'Confidence': 88, 'R/R': 2.5, 'Entry': 400.0, 'Stop': 380.0,
            'Target': 460.0, 'Rank Score': 70.0,
        },
    ])
    table = recommendation_rows(recs, 100_000, SETTINGS, {'SPY'})
    by_ticker = {r['Ticker']: r for _, r in table.iterrows()}
    assert by_ticker['AAA']['Type'] == 'Stock'
    assert by_ticker['SPY']['Type'] == 'ETF'
    assert by_ticker['AAA']['Add Shares'] is not None
    assert by_ticker['AAA']['Add $'] is not None


def test_recommendation_rows_sizes_held_names_against_current_value():
    recs = pd.DataFrame([
        {
            'Ticker': 'AAA', 'Company Name': 'Alpha', 'Setup': 'breakout',
            'Confidence': 90, 'R/R': 3.0, 'Entry': 100.0, 'Stop': 90.0,
            'Target': 130.0, 'Rank Score': 80.0,
        },
    ])
    fresh = recommendation_rows(recs, 100_000, SETTINGS, set())
    held = recommendation_rows(recs, 100_000, SETTINGS, set(), current_values={'AAA': 9_000.0})
    fresh_shares = fresh.iloc[0]['Add Shares']
    held_shares = held.iloc[0]['Add Shares']
    # Already holding $9k of a $100k book (10% cap) leaves only $1k of room,
    # so the suggested add must be smaller than a fresh full-size position.
    assert held_shares < fresh_shares



def test_rotation_candidates_ranks_weakest_first():
    monitor = pd.DataFrame([
        {'Ticker': 'STRONG', 'Sleeve': 'satellite', '% vs SMA200': 0.20,
         'Weight %': 0.05, 'Value': 500.0, 'Unreal P&L %': 0.10},
        {'Ticker': 'WEAK', 'Sleeve': 'satellite', '% vs SMA200': -0.15,
         'Weight %': 0.02, 'Value': 80.0, 'Unreal P&L %': -0.20},
        {'Ticker': 'VTI', 'Sleeve': 'core', '% vs SMA200': 0.10,
         'Weight %': 0.40, 'Value': 4000.0, 'Unreal P&L %': 0.05},
    ])
    analysis = pd.DataFrame([
        {'Ticker': 'STRONG', 'RS Outperformance': 8.0},
        {'Ticker': 'WEAK', 'RS Outperformance': -5.0},
    ])
    rotation = rotation_candidates(monitor, analysis, {'SPY'})
    assert list(rotation['Ticker']) == ['WEAK', 'STRONG']
    # Core excluded
    assert 'VTI' not in set(rotation['Ticker'])


def test_rotation_candidates_excludes_etfs():
    monitor = pd.DataFrame([
        {'Ticker': 'SPY', 'Sleeve': 'satellite', '% vs SMA200': 0.05,
         'Weight %': 0.10, 'Value': 1000.0, 'Unreal P&L %': 0.0},
    ])
    rotation = rotation_candidates(monitor, pd.DataFrame(), {'SPY'})
    assert rotation.empty


def test_rotation_candidates_no_sleeve():
    monitor = pd.DataFrame([{'Ticker': 'AAA'}])
    assert rotation_candidates(monitor, pd.DataFrame(), set()).empty
    assert rotation_candidates(None, pd.DataFrame(), set()).empty


def test_rotation_candidates_labels_accounts():
    monitor = pd.DataFrame([
        {'Ticker': 'STRONG', 'Account': 'Roth IRA', 'Sleeve': 'satellite',
         '% vs SMA200': 0.20, 'Weight %': 0.05, 'Value': 500.0, 'Unreal P&L %': 0.10},
        {'Ticker': 'WEAK', 'Account': 'Taxable', 'Sleeve': 'satellite',
         '% vs SMA200': -0.15, 'Weight %': 0.02, 'Value': 80.0, 'Unreal P&L %': -0.20},
    ])
    rotation = rotation_candidates(monitor, pd.DataFrame(), set())
    assert 'Account' in rotation.columns
    assert list(rotation['Ticker']) == ['WEAK', 'STRONG']
    assert list(rotation['Account']) == ['Taxable', 'Roth IRA']


def test_rotation_candidates_drops_empty_account_column():
    monitor = pd.DataFrame([
        {'Ticker': 'WEAK', 'Sleeve': 'satellite', '% vs SMA200': -0.15,
         'Weight %': 0.02, 'Value': 80.0, 'Unreal P&L %': -0.20},
    ])
    rotation = rotation_candidates(monitor, pd.DataFrame(), set())
    assert 'Account' not in rotation.columns


def _alloc(core_value, total_value, core_min=0.60, core_max=0.70):
    core_pct = core_value / total_value
    return AllocationStats(
        core_value=core_value,
        satellite_value=total_value - core_value,
        total_value=total_value,
        core_pct=core_pct,
        satellite_pct=1 - core_pct,
        target_min=core_min,
        target_max=core_max,
        within_band=core_min <= core_pct <= core_max,
        label='',
    )


def test_core_rebalance_under_floor():
    alloc = _alloc(core_value=5000.0, total_value=10_000.0)  # 50% core
    dollars, note = core_rebalance(alloc)
    assert dollars == 1000.0  # 0.60*10000 - 5000
    assert 'move' in note.lower()


def test_core_rebalance_over_ceiling():
    alloc = _alloc(core_value=8000.0, total_value=10_000.0)  # 80% core
    dollars, note = core_rebalance(alloc)
    assert dollars == -1000.0  # -(8000 - 0.70*10000)
    assert 'trim' in note.lower()


def test_core_rebalance_within_band():
    alloc = _alloc(core_value=6500.0, total_value=10_000.0)  # 65% core
    dollars, note = core_rebalance(alloc)
    assert dollars == 0.0
    assert 'within' in note.lower()


def test_core_rebalance_none():
    assert core_rebalance(None) == (0.0, '')

