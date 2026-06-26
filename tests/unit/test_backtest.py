import pandas as pd

from src.screener.backtest import (
    STOP,
    TARGET,
    BacktestParams,
    Trade,
    backtest_symbol,
    stats_to_frame,
    summarize,
    summarize_by_confidence,
    summarize_by_setup,
    trades_to_frame,
)
from src.screener.strategy import StrategyConfig

STRATEGY = StrategyConfig()
PARAMS = BacktestParams()


def _make_trade(r: float, setup: str = 'Breakout', confidence: float = 70.0, outcome: str = TARGET) -> Trade:
    ts = pd.Timestamp('2024-01-01')
    return Trade(
        ticker='AAA', setup_type=setup, confidence=confidence, market_context='Risk-On',
        entry_date=ts, entry_price=100.0, stop=95.0, target=110.0,
        exit_date=ts, exit_price=110.0, outcome=outcome, r_multiple=r, bars_held=5,
        planned_rr=2.0, mae_r=0.4, mfe_r=2.0,
    )


def test_summarize_computes_core_metrics():
    trades = [_make_trade(2.0), _make_trade(-1.0, outcome=STOP),
              _make_trade(3.0), _make_trade(-1.0, outcome=STOP)]
    stats = summarize(trades)
    assert stats.trades == 4
    assert stats.wins == 2
    assert stats.losses == 2
    assert stats.win_rate == 0.5
    assert stats.expectancy == 0.75
    assert stats.avg_win == 2.5
    assert stats.avg_loss == -1.0
    assert stats.profit_factor == 2.5


def test_summarize_empty_is_zeroed():
    stats = summarize([])
    assert stats.trades == 0
    assert stats.expectancy == 0.0
    assert stats.profit_factor == 0.0


def test_summarize_by_setup_groups_independently():
    trades = [_make_trade(2.0, setup='Breakout'), _make_trade(-1.0, setup='Pullback', outcome=STOP)]
    by_setup = summarize_by_setup(trades)
    assert set(by_setup) == {'Breakout', 'Pullback'}
    assert by_setup['Breakout'].win_rate == 1.0
    assert by_setup['Pullback'].win_rate == 0.0


def test_summarize_by_confidence_buckets_into_tiers():
    trades = [_make_trade(1.0, confidence=60), _make_trade(1.0, confidence=70),
              _make_trade(1.0, confidence=80), _make_trade(1.0, confidence=90)]
    tiers = summarize_by_confidence(trades)
    assert set(tiers) == {'50-64', '65-74', '75-84', '85-100'}


def test_frames_have_expected_columns():
    trades = [_make_trade(2.0)]
    assert {'Ticker', 'Setup', 'Outcome', 'R Multiple'}.issubset(trades_to_frame(trades).columns)
    stats_df = stats_to_frame(summarize_by_setup(trades))
    assert {'Group', 'Trades', 'Win Rate', 'Expectancy (R)'}.issubset(stats_df.columns)


# --- End-to-end bar replay -------------------------------------------------

def _benchmark(length: int) -> pd.Series:
    idx = pd.date_range('2023-01-01', periods=length, freq='B')
    return pd.Series([300.0 + i * 0.03 for i in range(length)], index=idx)


def _breakout_then(path: list[float]) -> list[float]:
    vals = [100.0 + i for i in range(200)]              # uptrend
    vals += [300.0 - j * (20.0 / 29) for j in range(30)]    # pullback
    vals += [280.0 + j * (26.0 / 19) for j in range(20)]    # recovery
    vals += [305.0, 306.0, 307.0, 306.0, 305.0, 306.0, 307.0, 306.0, 307.0]
    vals.append(313.0)                                  # breakout
    vals += path                                        # forward outcome path
    return vals


def _frame(close_values: list[float]) -> pd.DataFrame:
    idx = pd.date_range('2023-01-01', periods=len(close_values), freq='B')
    close = pd.Series(close_values, index=idx)
    vol = pd.Series([900_000.0] * len(close_values), index=idx)
    vol.iloc[259] = 1_600_000.0  # breakout-day volume expansion
    return pd.DataFrame({'Close': close, 'Volume': vol}, index=idx)


def test_breakout_reaching_target_is_a_win():
    closes = _breakout_then([316.0, 322.0, 330.0, 338.0, 345.0, 350.0])
    df = _frame(closes)
    trades = backtest_symbol('AAA', df, _benchmark(len(closes)), STRATEGY, PARAMS)
    assert trades
    targets = [t for t in trades if t.outcome == TARGET]
    assert targets
    assert all(t.r_multiple > 0 for t in targets)
    assert all(t.stop < t.entry_price < t.target for t in trades)


def test_breakout_hitting_stop_loses_one_r():
    closes = _breakout_then([308.0, 300.0, 290.0, 280.0, 272.0, 265.0])
    df = _frame(closes)
    trades = backtest_symbol('AAA', df, _benchmark(len(closes)), STRATEGY, PARAMS)
    stops = [t for t in trades if t.outcome == STOP]
    assert stops
    assert all(round(t.r_multiple, 6) == -1.0 for t in stops)


def test_insufficient_history_returns_no_trades():
    idx = pd.date_range('2023-01-01', periods=40, freq='B')
    df = pd.DataFrame({'Close': range(40), 'Volume': [1] * 40}, index=idx)
    assert backtest_symbol('AAA', df, _benchmark(40), STRATEGY, PARAMS) == []
