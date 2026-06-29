"""CLI: backtest entry-staging (suggested-add / starter-tranche) policies.

Research-only. Reuses cached Yahoo history and the production entry pipeline,
then compares deploying full size at entry against a starter tranche that
completes only on confirmation (``starter_frac`` now, the rest at
``+add_trigger_r``). Exits are held fixed across variants so the comparison
isolates the *entry-staging* decision the live ``suggested_add_fraction`` makes.

Two views are reported:

* **Per-signal R** -- expectancy, risk-adjusted EV (Sharpe) and total R, the
  same headline the stop backtest uses.
* **Portfolio** -- compounds each variant into an equity curve under a
  concurrent-position cap with conviction sizing, so the drawdown/CAGR trade-off
  of staging (smaller losses on failed entries vs. add slippage on winners) is
  judged the way the live book actually compounds.

Examples
--------
    python scripts/backtest_scalein.py                          # watchlist, 5y
    python scripts/backtest_scalein.py --universe sp500 --max-tickers 150 --period 10y
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
from src.backtest.runner import (  # noqa: E402
    GateConfig,
    Stats,
    _forward_arrays,
    generate_entries,
    scalein_variants,
    simulate_scalein_entries,
    summarize,
)
from src.backtest.stops import ScaleInParams, simulate_scalein  # noqa: E402
from src.config import load_settings  # noqa: E402
from src.data.cache import SQLiteCache  # noqa: E402
from src.data.universe import load_sp500_universe  # noqa: E402
from src.data.yahoo_client import YahooFinanceClient  # noqa: E402
from src.screener.advisor import _conviction_risk  # noqa: E402
from src.screener.strategy import StrategyConfig  # noqa: E402

BENCHMARK = 'SPY'

# (entry_date, exit_date, r_multiple, confidence)
Trade = tuple[pd.Timestamp, pd.Timestamp, float, float]


def _watchlist_raw() -> list[str]:
    path = ROOT / 'watchlist.txt'
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            out.append(line.upper())
    return out


def _universe_tickers(name: str, cache: SQLiteCache, max_tickers: int) -> list[str]:
    if name == 'sp500':
        tickers = list(load_sp500_universe(cache).tickers)
    else:
        tickers = _watchlist_raw()
    if max_tickers > 0:
        tickers = tickers[:max_tickers]
    return tickers


def _resolve_trades(
    entries, histories: dict[str, pd.DataFrame], atr_period: int, variant: ScaleInParams,
) -> list[Trade]:
    """Pair each entry with its staged exit date and R-multiple, sorted by date."""
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
            atr_cache[e.ticker] = atr(hf, lf, cf, atr_period).shift(1)
        high, low, close, atr_prev = _forward_arrays(df, e.date, atr_period, atr_cache[e.ticker])
        if len(high) == 0:
            continue
        res = simulate_scalein(e.entry, e.initial_stop, e.target, high, low, close, atr_prev, variant)
        if res is None or not math.isfinite(res.r_multiple):
            continue
        pos = df.index.get_loc(e.date)
        exit_pos = min(pos + max(res.bars_held, 1), len(df.index) - 1)
        trades.append((e.date, df.index[exit_pos], res.r_multiple, e.confidence))
    trades.sort(key=lambda t: t[0])
    return trades


def _drawdown(curve: list[float]) -> float:
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return mdd


def _cagr(start: float, end: float, years: float) -> float:
    return (end / start) ** (1 / years) - 1 if years > 0 and start > 0 else 0.0


def _equity_curve(
    trades: list[Trade], settings, max_concurrent: int, cost: float,
) -> tuple[float, list[float]]:
    """Compound trades into an equity curve under a concurrent-position cap."""
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


def _print_signal_table(stats: list[Stats]) -> None:
    header = (
        f"{'Policy':<26} {'Trades':>6} {'ExpR':>7} {'Win%':>6} "
        f"{'AvgW':>6} {'AvgL':>6} {'PF':>6} {'Sharpe':>7} {'TotR':>8}"
    )
    print(header)
    print('-' * len(header))
    for s in sorted(stats, key=lambda x: x.expectancy_r, reverse=True):
        pf = '  inf' if s.profit_factor == float('inf') else f'{s.profit_factor:6.2f}'
        print(
            f'{s.name:<26} {s.trades:>6} {s.expectancy_r:>7.3f} '
            f'{s.win_rate * 100:>5.1f}% {s.avg_win_r:>6.2f} {s.avg_loss_r:>6.2f} {pf} '
            f'{s.sharpe:>7.3f} {s.total_r:>8.1f}'
        )


def main() -> int:
    parser = argparse.ArgumentParser(description='Backtest entry-staging (suggested-add) policies.')
    parser.add_argument('--universe', choices=['watchlist', 'sp500'], default='watchlist')
    parser.add_argument('--period', default='5y', help='History period (e.g. 5y, 10y).')
    parser.add_argument('--max-tickers', type=int, default=80)
    parser.add_argument('--step', type=int, default=2, help='Bars between entry checks.')
    parser.add_argument('--cooldown', type=int, default=5, help='Bars to skip after an entry.')
    parser.add_argument('--cost-bps', type=float, default=10.0, help='Round-trip cost in bps.')
    parser.add_argument('--max-concurrent', type=int, default=10, help='Max simultaneous positions.')
    parser.add_argument('--regime', action='store_true', help='Only enter when SPY > its 200-day.')
    parser.add_argument('--min-confidence', type=float, default=None)
    parser.add_argument('--min-rr', type=float, default=None)
    args = parser.parse_args()

    settings = load_settings()
    cache = SQLiteCache(settings.cache_dir)
    client = YahooFinanceClient(settings=settings, cache=cache)
    strategy = StrategyConfig.from_settings(settings)
    gates = GateConfig(
        min_confidence=(
            args.min_confidence if args.min_confidence is not None else settings.rec_min_confidence
        ),
        min_reward_risk=(args.min_rr if args.min_rr is not None else settings.rec_min_reward_risk),
        min_avg_volume=settings.min_avg_volume,
        require_regime=args.regime,
    )

    tickers = _universe_tickers(args.universe, cache, args.max_tickers)
    if not tickers:
        print('No tickers to backtest.')
        return 1

    bench = client.fetch_history([BENCHMARK], period=args.period).get(BENCHMARK)
    if bench is None or bench.empty:
        print('Benchmark history unavailable.')
        return 1
    benchmark_close = bench['Close'].dropna()

    histories = client.fetch_history(tickers, period=args.period)
    entries = []
    for ticker in tickers:
        df = histories.get(ticker)
        if df is not None and not df.empty:
            entries.extend(
                generate_entries(ticker, df, benchmark_close, strategy, gates,
                                 step=args.step, cooldown_bars=args.cooldown)
            )

    print(
        f'\nUniverse: {args.universe} ({len(tickers)} tickers, {args.period}) | '
        f'entries: {len(entries)}\n'
    )
    if not entries:
        print('No entries generated; nothing to compare.')
        return 0

    variants = scalein_variants()

    # View 1: per-signal R expectancy.
    results = simulate_scalein_entries(entries, histories, variants, strategy.atr_period)
    stats = [summarize(v.name, results[v.name]) for v in variants]
    print('Per-signal R (exits fixed; only the entry staging differs):')
    _print_signal_table(stats)

    # View 2: compounded portfolio (the trade-off that actually matters).
    years = (benchmark_close.index[-1] - benchmark_close.index[0]).days / 365.25
    spy_ret = benchmark_close.iloc[-1] / benchmark_close.iloc[0] - 1.0
    cost = args.cost_bps / 10_000.0
    rows = []
    for v in variants:
        trades = _resolve_trades(entries, histories, strategy.atr_period, v)
        equity, curve = _equity_curve(trades, settings, args.max_concurrent, cost)
        monthly = pd.Series(curve).pct_change().dropna()
        sharpe = (monthly.mean() / monthly.std() * math.sqrt(252 / args.step)) if monthly.std() else 0.0
        rows.append((v.name, equity - 1.0, _cagr(1, equity, years), _drawdown(curve), sharpe))

    print(f'\nPortfolio (max {args.max_concurrent} concurrent, {args.cost_bps:.0f} bps, '
          f'{years:.1f}y, conviction sizing):')
    print(f'{"Policy":<26}{"TotRet":>9}{"CAGR":>8}{"MaxDD":>8}{"Sharpe":>8}')
    print('-' * 59)
    for name, tot, cagr, mdd, sharpe in sorted(rows, key=lambda x: x[2], reverse=True):
        print(f'{name:<26}{tot:>8.1%}{cagr:>8.1%}{mdd:>8.1%}{sharpe:>8.2f}')
    print(f'{"SPY hold":<26}{spy_ret:>8.1%}{_cagr(1, 1 + spy_ret, years):>8.1%}{"":>8}{"":>8}')

    print(
        '\nR-multiples = profit / initial risk. Staging trims losses on failed '
        'entries (only the starter is at risk) at the cost of add slippage on '
        'confirmed winners; judge by portfolio MaxDD/Sharpe, not ExpR alone.'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
