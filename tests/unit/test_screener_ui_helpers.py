import threading
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from src.ui.screener import (
    _filter_results_by_sector,
    _risk_plan_for_results,
    _screen_quality_summary,
    _screen_worker,
    _sector_summary,
    _setup_reason_summary,
    _state_get,
    _state_set,
    _sync_screen_worker_state,
)


def test_sector_summary_ranks_leaders_by_quality() -> None:
    results = pd.DataFrame(
        {
            'Ticker': ['A', 'B', 'C'],
            'Sector': ['Tech', 'Tech', 'Energy'],
            'Confidence': [80, 60, 40],
            'Rank Score': [90, 70, 50],
            'Sector Trend': [0.08, 0.03, -0.02],
        }
    )

    summary = _sector_summary(results)

    assert list(summary['Sector']) == ['Tech', 'Energy']
    assert summary.iloc[0]['Avg Confidence'] == 70.0
    assert summary.iloc[0]['Avg Rank Score'] == 80.0


def test_filter_results_by_sector_keeps_only_selected_groups() -> None:
    results = pd.DataFrame(
        {
            'Ticker': ['A', 'B', 'C'],
            'Sector': ['Tech', 'Health Care', 'Energy'],
            'Confidence': [70, 65, 55],
        }
    )

    filtered = _filter_results_by_sector(results, ('Tech',))

    assert list(filtered['Ticker']) == ['A']
    assert list(filtered['Sector']) == ['Tech']


def test_screen_quality_summary_reports_market_health() -> None:
    results = pd.DataFrame(
        {
            'Ticker': ['A', 'B', 'C'],
            'Sector': ['Tech', 'Tech', 'Energy'],
            'Confidence': [82, 76, 58],
            'Rank Score': [85, 72, 50],
            'Sector Trend': [0.12, 0.09, -0.03],
            'R/R': [2.5, 2.2, 1.2],
        }
    )

    summary = _screen_quality_summary(results)

    assert set(summary['Metric']) >= {'Market Breadth', 'Sector Leadership', 'Setup Quality'}
    assert summary[summary['Metric'] == 'Setup Quality']['Value'].iloc[0] in {'Strong', 'Moderate'}


def test_risk_plan_for_results_computes_position_size_from_stop_distance() -> None:
    results = pd.DataFrame({'Ticker': ['AAA'], 'Entry': [100.0], 'Stop': [95.0], 'Target': [120.0]})

    plan = _risk_plan_for_results(results, account_size=10_000.0, risk_pct=1.0)

    assert list(plan.columns)[:3] == ['Ticker', 'Entry', 'Stop']
    assert plan.iloc[0]['Risk Dollars'] == 100.0
    assert plan.iloc[0]['Risk Per Share'] == 5.0
    assert plan.iloc[0]['Shares'] == 20.0
    assert plan.iloc[0]['Position Value'] == 2_000.0


def test_setup_reason_summary_lists_key_driver_columns() -> None:
    results = pd.DataFrame(
        {
            'Ticker': ['AAA'],
            'Trend Score': [0.82],
            'RS Outperformance': [0.18],
            'Rel Volume': [1.8],
            'R/R': [2.8],
            'Entry Quality': ['Strong dip'],
        }
    )

    summary = _setup_reason_summary(results)

    assert list(summary.columns)[:3] == ['Ticker', 'Trend Score', 'RS Outperformance']
    assert summary.iloc[0]['Ticker'] == 'AAA'
    assert summary.iloc[0]['Key Driver'] in {'Trend leadership', 'Strong trend quality'}


def test_screen_worker_ignores_work_when_cancel_is_already_set() -> None:
    cancel_event = threading.Event()
    cancel_event.set()

    class DummyEngine:
        def _fetch_inputs(self, universe, force_refresh):
            raise AssertionError('fetch should not start after cancellation')

    with (
        patch('src.ui.screener.load_sp500_universe') as mock_load_universe,
        patch('src.ui.screener._state_set') as mock_state_set,
    ):
        _screen_worker(None, DummyEngine(), None, cancel_event)

    mock_load_universe.assert_not_called()
    assert any(call.args == ('screen_cancelled', True) for call in mock_state_set.call_args_list)
    assert any(call.args == ('screen_running', False) for call in mock_state_set.call_args_list)


def test_sync_screen_worker_state_exits_live_mode_when_worker_finishes() -> None:
    worker = threading.Thread(target=lambda: None)
    worker.start()
    worker.join()

    _state_set('screen_running', True)
    _state_set('screen_worker', worker)

    _sync_screen_worker_state()

    assert _state_get('screen_running') is False


def test_screen_worker_reruns_after_completion() -> None:
    cancel_event = threading.Event()

    class DummyEngine:
        def _fetch_inputs(self, universe, force_refresh):
            return SimpleNamespace(
                tickers=['AAA'],
                regime_ok=True,
                context=SimpleNamespace(label='Risk-On'),
            )

        def _evaluate_ticker(self, ticker, inputs, universe, config):
            return {'Ticker': ticker, 'Rank Score': 88.0}

    with (
        patch(
            'src.ui.screener.load_sp500_universe',
            return_value=SimpleNamespace(tickers=[], companies={}),
        ),
        patch('src.ui.screener.st.rerun') as mock_rerun,
    ):
        _screen_worker(None, DummyEngine(), None, cancel_event)

    mock_rerun.assert_called_once()


def test_screen_worker_cancels_mid_run() -> None:
    cancel_event = threading.Event()

    class DummyEngine:
        def _fetch_inputs(self, universe, force_refresh):
            return SimpleNamespace(
                tickers=['AAA', 'BBB'],
                regime_ok=True,
                context=SimpleNamespace(label='Risk-On'),
            )

        def _evaluate_ticker(self, ticker, inputs, universe, config):
            if ticker == 'AAA':
                cancel_event.set()
                return {'Ticker': ticker, 'Rank Score': 88.0}
            return {'Ticker': ticker, 'Rank Score': 79.0}

    with patch('src.ui.screener._state_set') as mock_state_set:
        _screen_worker(None, DummyEngine(), None, cancel_event)

    assert any(call.args == ('screen_cancelled', True) for call in mock_state_set.call_args_list)
    assert any(call.args == ('screen_running', False) for call in mock_state_set.call_args_list)
