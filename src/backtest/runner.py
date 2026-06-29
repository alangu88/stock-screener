"""Walk-forward entry generation and expectancy aggregation.

Entries are produced by replaying the *production* pipeline bar by bar: at each
historical date the OHLCV history is sliced up to that bar, features/setup/plan
are computed exactly as the live screener would, and an actionable immediate
entry is recorded. Each entry is then handed to :func:`simulate_trade` for every
stop variant, so all variants see an identical entry stream (a fair, apples-to
-apples comparison of *exits* only).

Entries are spaced by a fixed cooldown so the same signal is not re-counted on
consecutive bars; this is deliberately independent of the stop variant to keep
the entry stream identical across variants.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from src.analysis.features import MIN_BARS, compute_feature_panel, features_at
from src.analysis.indicators import atr, sma
from src.backtest.stops import StopParams, TradeResult, simulate_trade
from src.screener.ranking import confidence_score
from src.screener.setups import AVOID, detect_setup
from src.screener.strategy import StrategyConfig
from src.screener.trade_plan import build_trade_plan


@dataclass(frozen=True)
class Entry:
    ticker: str
    date: pd.Timestamp
    setup: str
    entry: float
    initial_stop: float
    target: float
    confidence: float
    reward_risk: float


@dataclass(frozen=True)
class GateConfig:
    """Entry gates mirroring the live screen (liquidity / quality / asymmetry)."""

    min_confidence: float = 45.0
    min_reward_risk: float = 1.5
    min_avg_volume: float = 500_000.0
    require_regime: bool = False  # only enter when SPY is above its long MA


def generate_entries(
    ticker: str,
    df: pd.DataFrame,
    benchmark_close: pd.Series,
    strategy: StrategyConfig,
    gates: GateConfig,
    *,
    step: int = 1,
    cooldown_bars: int = 5,
) -> list[Entry]:
    """Replay history for one ticker and collect actionable immediate entries.

    Only ``immediate_entry`` setups (breakout/pullback "buy now" signals) are
    taken; buy-stop contractions are excluded because their fill depends on a
    future trigger that this v1 harness does not simulate.
    """
    if df is None or df.empty or 'Close' not in df.columns:
        return []
    close = df['Close'].dropna()
    if len(close) < MIN_BARS + 2:
        return []

    entries: list[Entry] = []
    index = close.index
    cooldown_until = -1
    panel = compute_feature_panel(df, benchmark_close, strategy)
    if panel is None:
        return []
    regime_ok = None
    if gates.require_regime:
        bench = benchmark_close.reindex(index).ffill()
        regime_ok = bench >= sma(bench, strategy.ma_long)
    # Leave the final bar out so every entry has at least one forward bar.
    for pos in range(MIN_BARS, len(index) - 1, max(step, 1)):
        if pos <= cooldown_until:
            continue
        date = index[pos]
        if regime_ok is not None and not bool(regime_ok.iloc[pos]):
            continue
        features = features_at(panel, pos, strategy)
        if features is None:
            continue
        if features.avg_volume < gates.min_avg_volume:
            continue
        setup = detect_setup(features, strategy)
        if setup.setup_type == AVOID:
            continue
        plan = build_trade_plan(features, setup, strategy)
        if not plan.immediate_entry or plan.entry is None or plan.stop is None:
            continue
        if plan.reward_risk is None or plan.reward_risk < gates.min_reward_risk:
            continue
        confidence = confidence_score(features, setup, plan, strategy)
        if confidence < gates.min_confidence:
            continue
        entries.append(
            Entry(
                ticker=ticker,
                date=date,
                setup=setup.setup_type,
                entry=float(plan.entry),
                initial_stop=float(plan.stop),
                target=float(plan.target),
                confidence=float(confidence),
                reward_risk=float(plan.reward_risk),
            )
        )
        cooldown_until = pos + cooldown_bars
    return entries


def _forward_arrays(df: pd.DataFrame, entry_date: pd.Timestamp, atr_period: int,
                    atr_series: pd.Series | None = None):
    """Forward OHLC arrays (entry bar excluded) plus a prior-bar ATR series.

    Rows with a missing close are dropped and High/Low fall back to Close, so a
    gap in the longer histories cannot inject NaN into the simulated result.
    ``atr_series`` may be supplied precomputed (already ``.shift(1)``) to avoid
    recomputing ATR over the full history once per entry.
    """
    close_full = df['Close']
    high_full = df['High'] if 'High' in df.columns else close_full
    low_full = df['Low'] if 'Low' in df.columns else close_full
    if atr_series is None:
        atr_series = atr(high_full, low_full, close_full, atr_period).shift(1)

    pos = df.index.get_loc(entry_date)
    fwd = slice(pos + 1, len(df))
    close = close_full.iloc[fwd]
    valid = close.notna()
    close = close[valid]
    high = high_full.iloc[fwd][valid].fillna(close)
    low = low_full.iloc[fwd][valid].fillna(close)
    # atr_prev[i] is the ATR known before forward bar i (i.e. the prior bar).
    atr_prev = atr_series.iloc[fwd][valid].bfill().fillna(0.0)
    return (
        high.to_numpy(dtype=float),
        low.to_numpy(dtype=float),
        close.to_numpy(dtype=float),
        atr_prev.to_numpy(dtype=float),
    )


def simulate_entries(
    entries: list[Entry],
    histories: dict[str, pd.DataFrame],
    variants: list[StopParams],
    atr_period: int,
) -> dict[str, list[TradeResult]]:
    """Run every entry through every stop variant. Returns variant -> results."""
    results: dict[str, list[TradeResult]] = {v.name: [] for v in variants}
    atr_cache: dict[str, pd.Series] = {}
    for e in entries:
        df = histories.get(e.ticker)
        if df is None or e.date not in df.index:
            continue
        atr_series = atr_cache.get(e.ticker)
        if atr_series is None:
            close_full = df['Close']
            high_full = df['High'] if 'High' in df.columns else close_full
            low_full = df['Low'] if 'Low' in df.columns else close_full
            atr_series = atr(high_full, low_full, close_full, atr_period).shift(1)
            atr_cache[e.ticker] = atr_series
        high, low, close, atr_prev = _forward_arrays(df, e.date, atr_period, atr_series)
        if len(high) == 0:
            continue
        for v in variants:
            res = simulate_trade(
                e.entry, e.initial_stop, e.target, high, low, close, atr_prev, v
            )
            if res is not None:
                results[v.name].append(res)
    return results


@dataclass(frozen=True)
class Stats:
    name: str
    trades: int
    expectancy_r: float  # mean R -- the per-trade EV headline
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    profit_factor: float
    std_r: float
    sharpe: float  # expectancy / std (per-trade risk-adjusted EV)
    avg_bars: float
    r_per_bar: float  # expectancy / avg_bars (capital-efficiency / EV per unit time)
    total_r: float


def summarize(name: str, results: list[TradeResult]) -> Stats:
    finite = [r for r in results if math.isfinite(r.r_multiple)]
    n = len(finite)
    if n == 0:
        return Stats(name, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    rs = [r.r_multiple for r in finite]
    wins = [x for x in rs if x > 0]
    losses = [x for x in rs if x <= 0]
    total = sum(rs)
    mean = total / n
    var = sum((x - mean) ** 2 for x in rs) / n
    std = math.sqrt(var)
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = gross_win / gross_loss if gross_loss > 0 else math.inf
    avg_bars = sum(r.bars_held for r in finite) / n
    return Stats(
        name=name,
        trades=n,
        expectancy_r=mean,
        win_rate=len(wins) / n,
        avg_win_r=(gross_win / len(wins)) if wins else 0.0,
        avg_loss_r=(sum(losses) / len(losses)) if losses else 0.0,
        profit_factor=profit_factor,
        std_r=std,
        sharpe=(mean / std) if std > 0 else 0.0,
        avg_bars=avg_bars,
        r_per_bar=(mean / avg_bars) if avg_bars > 0 else 0.0,
        total_r=total,
    )


def default_variants() -> list[StopParams]:
    """A representative sweep from the current static stop to trailing systems."""
    return [
        # Approximates today's behavior: fixed initial stop, exit at target.
        StopParams(name='Structural (current)', target_exit=True),
        StopParams(name='Chandelier 2.0x', chandelier_atr_mult=2.0, target_exit=False),
        StopParams(name='Chandelier 2.5x', chandelier_atr_mult=2.5, target_exit=False),
        StopParams(name='Chandelier 3.0x', chandelier_atr_mult=3.0, target_exit=False),
        StopParams(
            name='BE@1R + Chandelier 3.0x',
            chandelier_atr_mult=3.0,
            breakeven_r=1.0,
            target_exit=False,
        ),
        StopParams(
            name='BE@1R + 1/3 @ 2R + Chand 3.0x',
            chandelier_atr_mult=3.0,
            breakeven_r=1.0,
            partial_r=2.0,
            partial_frac=1 / 3,
            target_exit=False,
        ),
        StopParams(
            name='Time20 + Chandelier 3.0x',
            chandelier_atr_mult=3.0,
            time_stop_bars=20,
            min_progress_r=0.5,
            target_exit=False,
        ),
    ]
