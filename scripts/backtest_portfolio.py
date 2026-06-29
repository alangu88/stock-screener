"""CLI: portfolio-level equity-curve backtest vs SPY buy-and-hold.

Compounds the production entry stream into an equity curve: each closed trade
moves equity by ``risk_pct * R``, where ``risk_pct`` scales with confidence
(conviction sizing, hard-capped at 2%). Round-trip cost is charged in basis
points. Reports CAGR, total return, max drawdown and Sharpe against SPY total
return over the same window so outperformance can be judged honestly.

Research-only; reuses cached Yahoo history and the live entry pipeline.

Example
-------
    python scripts/backtest_portfolio.py --universe sp500 --period 10y --max-tickers 150
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.indicators import atr  # noqa: E402
from src.backtest.runner import GateConfig, _forward_arrays, generate_entries  # noqa: E402
from src.backtest.stops import StopParams, simulate_trade  # noqa: E402
from src.config import load_settings  # noqa: E402
from src.data.cache import SQLiteCache  # noqa: E402
from src.data.universe import load_sp500_universe  # noqa: E402
from src.data.yahoo_client import YahooFinanceClient  # noqa: E402
from src.screener.advisor import _conviction_risk  # noqa: E402
from src.screener.strategy import StrategyConfig  # noqa: E402

BENCHMARK = 'SPY'


def _drawdown(curve: list[float]) -> float:
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return mdd


def _cagr(start: float, end: float, years: float) -> float:
    return (end / start) ** (1 / years) - 1 if years > 0 and start > 0 else 0.0


# (entry_date, exit_date, r_multiple, confidence)
Trade = tuple[pd.Timestamp, pd.Timestamp, float, float]


def _resolve_trades(
    entries, histories: dict[str, pd.DataFrame], strategy: StrategyConfig, variant: StopParams,
) -> list[Trade]:
    """Pair each entry with its simulated exit date and R-multiple, sorted by date."""
    trades: list[Trade] = []
    atr_cache: dict[str, pd.Series] = {}
    for e in entries:
        df = histories.get(e.ticker)
        if df is None or e.date not in df.index:
            continue
        if e.ticker not in atr_cache:
            cf = df['Close']
            hf = df['High'] if 'High' in df.columns else cf
            lf = df['Low'] if 'Low' in df.columns else cf
            atr_cache[e.ticker] = atr(hf, lf, cf, strategy.atr_period).shift(1)
        high, low, close, atr_prev = _forward_arrays(df, e.date, strategy.atr_period, atr_cache[e.ticker])
        if len(high) == 0:
            continue
        res = simulate_trade(e.entry, e.initial_stop, e.target, high, low, close, atr_prev, variant)
        if res is None or not math.isfinite(res.r_multiple):
            continue
        pos = df.index.get_loc(e.date)
        exit_pos = min(pos + max(res.bars_held, 1), len(df.index) - 1)
        trades.append((e.date, df.index[exit_pos], res.r_multiple, e.confidence))
    trades.sort(key=lambda t: t[0])
    return trades


def _equity_curve(
    trades: list[Trade], settings, max_concurrent: int, cost: float,
) -> tuple[float, list[float]]:
    """Compound trades into an equity curve under a concurrent-position cap.

    Equity is allocated at entry and realized at exit so concurrent trades share
    capital (no fake leverage); risk per trade scales with conviction (2% cap).
    """
    equity = 1.0
    open_pos: list[tuple[pd.Timestamp, float, float]] = []  # (exit, alloc, r)
    events: list[tuple[pd.Timestamp, float]] = []
    for entry_date, exit_date, r_mult, conf in trades:
        matured = [op for op in open_pos if op[0] <= entry_date]
        open_pos = [op for op in open_pos if op[0] > entry_date]
        for ex, alloc, r in sorted(matured):
            equity += alloc * (r - cost)
            events.append((ex, equity))
        if len(open_pos) >= max_concurrent:
            continue
        alloc = equity * _conviction_risk(settings, conf)
        open_pos.append((exit_date, alloc, r_mult))
    for ex, alloc, r in sorted(open_pos):
        equity += alloc * (r - cost)
        events.append((ex, equity))
    events.sort(key=lambda x: x[0])
    return equity, [1.0] + [e for _, e in events]


def main() -> int:
    p = argparse.ArgumentParser(description='Portfolio equity-curve backtest vs SPY.')
    p.add_argument('--universe', choices=['sp500'], default='sp500')
    p.add_argument('--period', default='10y')
    p.add_argument('--max-tickers', type=int, default=150)
    p.add_argument('--step', type=int, default=2)
    p.add_argument('--cost-bps', type=float, default=10.0, help='Round-trip cost in bps.')
    p.add_argument('--max-concurrent', type=int, default=10, help='Max simultaneous positions.')
    p.add_argument('--regime', action='store_true', help='Only enter when SPY is above its 200-day.')
    p.add_argument('--min-rr', type=float, default=None)
    p.add_argument('--min-confidence', type=float, default=None)
    args = p.parse_args()

    settings = load_settings()
    cache = SQLiteCache(settings.cache_dir)
    client = YahooFinanceClient(settings=settings, cache=cache)
    strategy = StrategyConfig.from_settings(settings)
    min_conf = args.min_confidence if args.min_confidence is not None else settings.rec_min_confidence
    gates = GateConfig(
        min_confidence=min_conf,
        min_reward_risk=args.min_rr if args.min_rr is not None else settings.rec_min_reward_risk,
        min_avg_volume=settings.min_avg_volume,
        require_regime=args.regime,
    )

    tickers = list(load_sp500_universe(cache).tickers)[: args.max_tickers]
    bench = client.fetch_history([BENCHMARK], period=args.period)[BENCHMARK]['Close'].dropna()
    histories = client.fetch_history(tickers, period=args.period)

    entries = []
    for t in tickers:
        df = histories.get(t)
        if df is not None and not df.empty:
            entries.extend(generate_entries(t, df, bench, strategy, gates, step=args.step))
    if not entries:
        print('No entries generated.')
        return 0

    variant = StopParams(name='BE@1R + 1/3@2R + Chand 3.0x', chandelier_atr_mult=3.0,
                         breakeven_r=1.0, partial_r=2.0, partial_frac=1 / 3, target_exit=False)
    trades = _resolve_trades(entries, histories, strategy, variant)
    equity, curve = _equity_curve(trades, settings, args.max_concurrent, args.cost_bps / 10_000.0)

    years = (bench.index[-1] - bench.index[0]).days / 365.25
    spy_ret = bench.iloc[-1] / bench.iloc[0] - 1.0
    monthly = pd.Series(curve).pct_change().dropna()
    sharpe = (monthly.mean() / monthly.std() * math.sqrt(252 / args.step)) if monthly.std() else 0.0

    print(f'\nTrades: {len(trades)} | window: {years:.1f}y | cost: {args.cost_bps:.0f} bps round-trip')
    print(f'{"Strategy":<14}{"TotRet":>9}{"CAGR":>8}{"MaxDD":>8}{"Sharpe":>8}')
    print('-' * 47)
    print(f'{"Portfolio":<14}{equity-1:>8.1%}{_cagr(1,equity,years):>8.1%}'
          f'{_drawdown(curve):>8.1%}{sharpe:>8.2f}')
    print(f'{"SPY hold":<14}{spy_ret:>8.1%}{_cagr(1,1+spy_ret,years):>8.1%}{"":>8}{"":>8}')
    edge = _cagr(1, equity, years) - _cagr(1, 1 + spy_ret, years)
    print(f'\nCAGR edge vs SPY: {edge:+.1%}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
