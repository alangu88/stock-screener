"""Historical backtesting (bar-replay simulation).

Replays the *exact same* live pipeline -- ``compute_features`` ->
``detect_setup`` -> ``build_trade_plan`` -> ``confidence_score`` -- at each
historical bar, using only data available up to that bar (no look-ahead). When
an actionable setup appears, the planned entry/stop/target are simulated
forward against subsequent highs/lows to record the realized outcome.

The point is *validation*, not a profitability claim: it measures whether the
methodology's quality ordering holds up (do higher-quality setups and higher
confidence scores predict better results?). It is a daily-bar simulation
-- fills are assumed at the planned levels, with no slippage or commissions,
and the S&P 500 universe is survivorship-biased -- so treat absolute numbers as
optimistic and focus on *relative* comparisons.

When stop and target are both touched in the same bar, the stop is assumed to
trigger first (conservative).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.analysis.features import MIN_BARS, compute_features
from src.screener.ranking import assess_market_context, confidence_score
from src.screener.setups import AVOID, detect_setup
from src.screener.strategy import StrategyConfig
from src.screener.trade_plan import TradePlan, build_trade_plan

TARGET = 'target'
STOP = 'stop'
TIMEOUT = 'timeout'

# Confidence buckets used to test whether the score predicts results. The label
# text and the boundaries in ``_confidence_tier`` are the single shared source.
_CONFIDENCE_TIERS = ('50-64', '65-74', '75-84', '85-100')


@dataclass(frozen=True)
class BacktestParams:
    min_confidence: float = 50.0
    max_holding_bars: int = 40   # exit at market if neither level hit
    entry_window: int = 5        # bars allowed for a buy-stop to trigger
    cooldown_bars: int = 3       # quiet period after an exit before re-entry
    step: int = 1                # evaluate every Nth bar (speed vs resolution)


@dataclass(frozen=True)
class Trade:
    ticker: str
    setup_type: str
    confidence: float
    market_context: str
    entry_date: pd.Timestamp
    entry_price: float
    stop: float
    target: float
    exit_date: pd.Timestamp
    exit_price: float
    outcome: str  # TARGET | STOP | TIMEOUT
    r_multiple: float
    bars_held: int
    planned_rr: float   # (target - entry) / (entry - stop) at signal time
    mae_r: float        # max adverse excursion before exit, in R (heat taken)
    mfe_r: float        # max favorable excursion before exit, in R (best unrealized)


@dataclass(frozen=True)
class PerformanceStats:
    trades: int
    wins: int
    losses: int
    win_rate: float
    expectancy: float      # mean R-multiple per trade
    avg_win: float         # mean R of winners
    avg_loss: float        # mean R of losers
    profit_factor: float   # gross win R / gross loss R
    avg_bars_held: float
    avg_confidence: float

    @classmethod
    def empty(cls) -> PerformanceStats:
        return cls(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class _PriceSeries:
    """Aligned date/OHLC arrays for one symbol, indexed by bar position."""

    dates: pd.DatetimeIndex
    closes: np.ndarray
    highs: np.ndarray
    lows: np.ndarray

    @property
    def bar_count(self) -> int:
        return len(self.closes)


@dataclass(frozen=True)
class _Signal:
    """An actionable, confident setup with its trade plan at a given bar."""

    setup_type: str
    confidence: float
    plan: TradePlan


def backtest_symbol(
    ticker: str,
    df: pd.DataFrame | None,
    benchmark_close: pd.Series,
    strategy: StrategyConfig,
    params: BacktestParams,
) -> list[Trade]:
    """Replay one symbol's history and return every simulated trade."""
    if df is None or df.empty or 'Close' not in df.columns or 'Volume' not in df.columns:
        return []

    close = df['Close'].dropna()
    # Wait until the longest indicator window (200-day MA / 52-week range) is
    # warm; before that, those values fall back to price and distort setups.
    warmup = max(MIN_BARS, strategy.high_low_window)
    if len(close) < warmup + 2:
        return []

    df = df.loc[close.index]
    series = _PriceSeries(
        dates=close.index,
        closes=close.to_numpy(dtype=float),
        highs=_price_column(df, 'High', close),
        lows=_price_column(df, 'Low', close),
    )

    trades: list[Trade] = []
    bar = warmup
    while bar < series.bar_count - 1:
        signal = _signal_at(df, benchmark_close, series.dates, bar, strategy, params)
        if signal is None:
            bar += params.step
            continue

        entry_bar = _resolve_entry(bar, signal.plan, series.highs, series.bar_count, params)
        if entry_bar is None:
            bar += params.step
            continue

        context = assess_market_context(benchmark_close.loc[: series.dates[bar]], strategy)
        trade, exit_bar = _simulate(series, ticker, signal, context.label, entry_bar, params)
        trades.append(trade)
        bar = exit_bar + params.cooldown_bars + 1

    return trades


def backtest_universe(
    history: dict[str, pd.DataFrame],
    benchmark_close: pd.Series,
    strategy: StrategyConfig,
    params: BacktestParams,
) -> list[Trade]:
    trades: list[Trade] = []
    for ticker, df in history.items():
        trades.extend(backtest_symbol(ticker, df, benchmark_close, strategy, params))
    return trades


def summarize(trades: list[Trade]) -> PerformanceStats:
    if not trades:
        return PerformanceStats.empty()

    r_multiples = [t.r_multiple for t in trades]
    wins = [r for r in r_multiples if r > 0]
    losses = [r for r in r_multiples if r <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    return PerformanceStats(
        trades=len(trades),
        wins=len(wins),
        losses=len(losses),
        win_rate=len(wins) / len(trades),
        expectancy=sum(r_multiples) / len(trades),
        avg_win=gross_win / len(wins) if wins else 0.0,
        avg_loss=sum(losses) / len(losses) if losses else 0.0,
        profit_factor=_profit_factor(gross_win, gross_loss),
        avg_bars_held=sum(t.bars_held for t in trades) / len(trades),
        avg_confidence=sum(t.confidence for t in trades) / len(trades),
    )


def summarize_by_setup(trades: list[Trade]) -> dict[str, PerformanceStats]:
    groups: dict[str, list[Trade]] = {}
    for trade in trades:
        groups.setdefault(trade.setup_type, []).append(trade)
    return {setup: summarize(group) for setup, group in groups.items()}


def summarize_by_confidence(trades: list[Trade]) -> dict[str, PerformanceStats]:
    """Bucket trades by confidence tier to test whether the score predicts results."""
    groups: dict[str, list[Trade]] = {tier: [] for tier in _CONFIDENCE_TIERS}
    for trade in trades:
        groups[_confidence_tier(trade.confidence)].append(trade)
    return {tier: summarize(group) for tier, group in groups.items() if group}


def trades_to_frame(trades: list[Trade]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            'Ticker': t.ticker,
            'Setup': t.setup_type,
            'Confidence': t.confidence,
            'Context': t.market_context,
            'Entry Date': t.entry_date,
            'Entry': t.entry_price,
            'Stop': t.stop,
            'Target': t.target,
            'Exit Date': t.exit_date,
            'Exit': t.exit_price,
            'Outcome': t.outcome,
            'R Multiple': t.r_multiple,
            'Bars Held': t.bars_held,
            'Planned RR': t.planned_rr,
            'MAE (R)': t.mae_r,
            'MFE (R)': t.mfe_r,
        }
        for t in trades
    )


def stats_to_frame(named_stats: dict[str, PerformanceStats]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            'Group': name,
            'Trades': s.trades,
            'Win Rate': s.win_rate,
            'Expectancy (R)': s.expectancy,
            'Avg Win (R)': s.avg_win,
            'Avg Loss (R)': s.avg_loss,
            'Profit Factor': s.profit_factor,
            'Avg Bars Held': s.avg_bars_held,
        }
        for name, s in named_stats.items()
    )


def _signal_at(
    df: pd.DataFrame,
    benchmark_close: pd.Series,
    dates: pd.DatetimeIndex,
    bar: int,
    strategy: StrategyConfig,
    params: BacktestParams,
) -> _Signal | None:
    """Run the live funnel at ``bar``; return a tradeable signal or ``None``."""
    features = compute_features(df.iloc[: bar + 1], benchmark_close.loc[: dates[bar]], strategy)
    if features is None:
        return None

    setup = detect_setup(features, strategy)
    if setup.setup_type == AVOID:
        return None

    plan = build_trade_plan(features, setup, strategy)
    if plan.entry is None or plan.reward_risk is None or plan.entry - plan.stop <= 0:
        return None  # no plan, or a non-positive risk we can't size against

    confidence = confidence_score(features, setup, plan, strategy)
    if confidence < params.min_confidence:
        return None

    return _Signal(setup.setup_type, confidence, plan)


def _resolve_entry(
    signal_bar: int, plan: TradePlan, highs: np.ndarray, bar_count: int, params: BacktestParams
) -> int | None:
    """Bar where the entry fills, or ``None`` if a buy-stop never triggers."""
    if plan.immediate_entry:
        return signal_bar
    deadline = min(signal_bar + params.entry_window, bar_count - 1)
    for bar in range(signal_bar + 1, deadline + 1):
        if highs[bar] >= plan.entry:
            return bar
    return None


def _simulate(
    series: _PriceSeries,
    ticker: str,
    signal: _Signal,
    context_label: str,
    entry_bar: int,
    params: BacktestParams,
) -> tuple[Trade, int]:
    """Walk bars forward from entry until a level is hit or the holding cap is reached."""
    plan = signal.plan
    entry, stop, target = plan.entry, plan.stop, plan.target
    risk = entry - stop
    deadline = min(entry_bar + params.max_holding_bars, series.bar_count - 1)

    mae = mfe = 0.0
    for bar in range(entry_bar + 1, deadline + 1):
        mae = max(mae, (entry - series.lows[bar]) / risk)
        mfe = max(mfe, (series.highs[bar] - entry) / risk)
        if series.lows[bar] <= stop:  # stop-first on an inside bar (conservative)
            return _close_trade(series, ticker, signal, context_label, entry_bar, bar, stop, STOP, mae, mfe), bar
        if series.highs[bar] >= target:
            return _close_trade(series, ticker, signal, context_label, entry_bar, bar, target, TARGET, mae, mfe), bar

    exit_price = float(series.closes[deadline])
    return _close_trade(series, ticker, signal, context_label, entry_bar, deadline, exit_price, TIMEOUT, mae, mfe), deadline


def _close_trade(
    series: _PriceSeries,
    ticker: str,
    signal: _Signal,
    context_label: str,
    entry_bar: int,
    exit_bar: int,
    exit_price: float,
    outcome: str,
    mae_r: float,
    mfe_r: float,
) -> Trade:
    plan = signal.plan
    risk = plan.entry - plan.stop
    return Trade(
        ticker=ticker,
        setup_type=signal.setup_type,
        confidence=signal.confidence,
        market_context=context_label,
        entry_date=series.dates[entry_bar],
        entry_price=plan.entry,
        stop=plan.stop,
        target=plan.target,
        exit_date=series.dates[exit_bar],
        exit_price=exit_price,
        outcome=outcome,
        r_multiple=(exit_price - plan.entry) / risk,
        bars_held=exit_bar - entry_bar,
        planned_rr=plan.reward_risk,
        mae_r=mae_r,
        mfe_r=mfe_r,
    )


def _profit_factor(gross_win: float, gross_loss: float) -> float:
    if gross_loss > 0:
        return gross_win / gross_loss
    return float('inf') if gross_win > 0 else 0.0


def _price_column(df: pd.DataFrame, column: str, close: pd.Series) -> np.ndarray:
    """Return ``column`` aligned to ``close``'s index, defaulting to close when absent."""
    series = df[column].reindex(close.index).fillna(close) if column in df.columns else close
    return series.to_numpy(dtype=float)


def _confidence_tier(confidence: float) -> str:
    if confidence < 65:
        return '50-64'
    if confidence < 75:
        return '65-74'
    if confidence < 85:
        return '75-84'
    return '85-100'
