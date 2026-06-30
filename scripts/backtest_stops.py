"""CLI: backtest exit/stop strategies and compare their expectancy.

Research-only. Reuses cached Yahoo history and the production entry pipeline,
then reports each stop variant's expectancy in R-multiples so a change to the
live stop methodology can be justified by evidence before implementation.

Examples
--------
    python scripts/backtest_stops.py                     # watchlist, 2y
    python scripts/backtest_stops.py --universe sp500 --max-tickers 120
    python scripts/backtest_stops.py --period 5y --step 2 --by-setup
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backtest.runner import (  # noqa: E402
    GateConfig,
    Stats,
    default_variants,
    generate_entries,
    simulate_entries,
    summarize,
)
from src.config import load_settings  # noqa: E402
from src.data.cache import SQLiteCache  # noqa: E402
from src.data.universe import load_sp500_universe  # noqa: E402
from src.data.yahoo_client import YahooFinanceClient  # noqa: E402
from src.screener.strategy import StrategyConfig  # noqa: E402

BENCHMARK = 'SPY'

# Named stress windows (entry-date filters) for event-driven backtests.
EVENTS = {
    '2018 Q4 selloff': ('2018-10-01', '2019-01-31'),
    'COVID crash': ('2020-02-15', '2020-06-30'),
    '2022 bear': ('2022-01-01', '2022-12-31'),
    'SVB / 2023 banks': ('2023-02-15', '2023-05-15'),
    '2025 tariff shock': ('2025-02-01', '2025-06-30'),
}

_WORKER_CTX: dict = {}


def _worker_init(benchmark_close, strategy, gates, step, cooldown) -> None:
    _WORKER_CTX.update(
        benchmark_close=benchmark_close, strategy=strategy, gates=gates,
        step=step, cooldown=cooldown,
    )


def _gen_one(item):
    ticker, df = item
    if df is None or df.empty:
        return []
    return generate_entries(
        ticker, df, _WORKER_CTX['benchmark_close'], _WORKER_CTX['strategy'],
        _WORKER_CTX['gates'], step=_WORKER_CTX['step'], cooldown_bars=_WORKER_CTX['cooldown'],
    )


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


def _print_table(stats: list[Stats]) -> None:
    header = (
        f"{'Strategy':<32} {'Trades':>6} {'ExpR':>7} {'R/bar':>7} {'Win%':>6} "
        f"{'AvgW':>6} {'AvgL':>6} {'PF':>6} {'Sharpe':>7} {'Bars':>6} {'TotR':>8}"
    )
    print(header)
    print('-' * len(header))
    for s in sorted(stats, key=lambda x: x.expectancy_r, reverse=True):
        pf = '  inf' if s.profit_factor == float('inf') else f'{s.profit_factor:6.2f}'
        print(
            f'{s.name:<32} {s.trades:>6} {s.expectancy_r:>7.3f} {s.r_per_bar:>7.4f} '
            f'{s.win_rate * 100:>5.1f}% {s.avg_win_r:>6.2f} {s.avg_loss_r:>6.2f} {pf} '
            f'{s.sharpe:>7.3f} {s.avg_bars:>6.1f} {s.total_r:>8.1f}'
        )


def main() -> int:
    parser = argparse.ArgumentParser(description='Backtest exit/stop strategies.')
    parser.add_argument('--universe', choices=['watchlist', 'sp500'], default='watchlist')
    parser.add_argument('--period', default='2y', help='History period (e.g. 2y, 5y).')
    parser.add_argument('--max-tickers', type=int, default=80)
    parser.add_argument('--step', type=int, default=1, help='Bars between entry checks.')
    parser.add_argument('--cooldown', type=int, default=5, help='Bars to skip after an entry.')
    parser.add_argument('--workers', type=int, default=1, help='Parallel processes for entries.')
    parser.add_argument(
        '--regime', action='store_true',
        help='Only enter when SPY is above its 200-day MA (risk-on filter).'
    )
    parser.add_argument('--force-refresh', action='store_true', help='Bypass the cache.')
    parser.add_argument('--by-setup', action='store_true', help='Also break down by setup.')
    parser.add_argument(
        '--by-confidence', action='store_true',
        help='Break down expectancy by confidence band (model calibration check).'
    )
    parser.add_argument(
        '--events', action='store_true',
        help='Break down expectancy by major market-stress windows (entry date).'
    )
    parser.add_argument(
        '--min-confidence', type=float, default=None,
        help='Override the entry confidence gate (default: rec gate from settings).',
    )
    parser.add_argument(
        '--min-rr', type=float, default=None,
        help='Override the entry reward/risk gate (default: rec gate from settings).',
    )
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

    bench_hist = client.fetch_history([BENCHMARK], period=args.period, force_refresh=args.force_refresh)
    bench_df = bench_hist.get(BENCHMARK)
    if bench_df is None or bench_df.empty:
        print('Benchmark history unavailable.')
        return 1
    benchmark_close = bench_df['Close'].dropna()

    histories = client.fetch_history(tickers, period=args.period, force_refresh=args.force_refresh)

    all_entries = []
    items = [(t, histories.get(t)) for t in tickers]
    if args.workers > 1:
        with ProcessPoolExecutor(
            max_workers=args.workers,
            initializer=_worker_init,
            initargs=(benchmark_close, strategy, gates, args.step, args.cooldown),
        ) as pool:
            for entries in pool.map(_gen_one, items):
                all_entries.extend(entries)
    else:
        for ticker in tickers:
            df = histories.get(ticker)
            if df is None or df.empty:
                continue
            all_entries.extend(
                generate_entries(
                    ticker, df, benchmark_close, strategy, gates,
                    step=args.step, cooldown_bars=args.cooldown,
                )
            )

    print(
        f'\nUniverse: {args.universe} ({len(tickers)} tickers, {args.period}) | '
        f'entries: {len(all_entries)}\n'
    )
    if not all_entries:
        print('No entries generated; nothing to compare.')
        return 0

    variants = default_variants()
    results = simulate_entries(all_entries, histories, variants, strategy.atr_period)
    stats = [summarize(v.name, results[v.name]) for v in variants]
    _print_table(stats)

    if args.by_setup:
        for setup in sorted({e.setup for e in all_entries}):
            subset = [e for e in all_entries if e.setup == setup]
            sub_results = simulate_entries(subset, histories, variants, strategy.atr_period)
            sub_stats = [summarize(v.name, sub_results[v.name]) for v in variants]
            print(f'\n--- Setup: {setup} ({len(subset)} entries) ---')
            _print_table(sub_stats)

    if args.by_confidence:
        bands = [(0, 80), (80, 85), (85, 90), (90, 95), (95, 100.01)]
        structural = next(v for v in variants if v.name.startswith('Structural'))
        print('\n--- Calibration: Structural expectancy by confidence band ---')
        print(f"{'Band':<12} {'Trades':>6} {'ExpR':>7} {'Win%':>6} {'PF':>6} {'TotR':>8}")
        print('-' * 48)
        for lo, hi in bands:
            subset = [e for e in all_entries if lo <= e.confidence < hi]
            if not subset:
                continue
            sub_results = simulate_entries(subset, histories, variants, strategy.atr_period)
            s = summarize(structural.name, sub_results[structural.name])
            pf = ' inf' if s.profit_factor == float('inf') else f'{s.profit_factor:6.2f}'
            print(
                f'{f"{lo:g}-{hi:g}":<12} {s.trades:>6} {s.expectancy_r:>7.3f} '
                f'{s.win_rate * 100:>5.1f}% {pf} {s.total_r:>8.1f}'
            )

    if args.events:
        for name, (start, end) in EVENTS.items():
            lo, hi = pd.Timestamp(start), pd.Timestamp(end)
            subset = [e for e in all_entries if lo <= e.date <= hi]
            if not subset:
                print(f'\n--- Event: {name} ({start} -> {end}) | no entries ---')
                continue
            sub_results = simulate_entries(subset, histories, variants, strategy.atr_period)
            sub_stats = [summarize(v.name, sub_results[v.name]) for v in variants]
            print(f'\n--- Event: {name} ({start} -> {end}) | {len(subset)} entries ---')
            _print_table(sub_stats)

    print(
        '\nR-multiples = profit / initial risk (entry - initial stop). '
        'ExpR is the EV headline; PF = gross win / gross loss.'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
