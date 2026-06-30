"""Research-only: which features separate strong breakouts from weak ones.

Replays the production pipeline bar-by-bar (no look-ahead), keeps only confirmed
Breakout entries that clear the live gates, records each entry's feature
snapshot together with its realized Structural-stop R-multiple, then buckets by
candidate predictors so a breakout-specific filter can be justified by evidence
before touching the live screen.

    python scripts/research_breakout.py --max-tickers 250 --period 10y --workers 4
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

from src.analysis.features import MIN_BARS, compute_feature_panel, features_at  # noqa: E402
from src.analysis.indicators import atr, sma  # noqa: E402
from src.backtest.runner import _forward_arrays  # noqa: E402
from src.backtest.stops import StopParams, simulate_trade  # noqa: E402
from src.config import load_settings  # noqa: E402
from src.data.cache import SQLiteCache  # noqa: E402
from src.data.universe import load_sp500_universe  # noqa: E402
from src.data.yahoo_client import YahooFinanceClient  # noqa: E402
from src.screener.ranking import confidence_score  # noqa: E402
from src.screener.setups import BREAKOUT, detect_setup  # noqa: E402
from src.screener.strategy import StrategyConfig  # noqa: E402
from src.screener.trade_plan import build_trade_plan  # noqa: E402

BENCHMARK = 'SPY'
STRUCTURAL = StopParams(name='Structural', target_exit=True)

# (label, extractor) for each candidate breakout-quality predictor.
PREDICTORS: list[tuple[str, callable]] = [
    ('rel_volume (surge)', lambda f: f.rel_volume),
    ('base_depth', lambda f: f.base_depth),
    ('atr_pct', lambda f: f.atr_pct),
    ('rs_outperformance', lambda f: f.rs_outperformance),
    ('updown_volume_ratio', lambda f: f.updown_volume_ratio),
    ('obv_slope', lambda f: f.obv_slope),
    ('contraction_ratio', lambda f: f.contraction_ratio),
    ('pct_from_high', lambda f: f.pct_from_high),
    ('trend_score', lambda f: f.trend_score),
    ('ext_into_breakout', lambda f: (f.price - f.pivot) / f.pivot if f.pivot else 0.0),
]

_WORKER_CTX: dict = {}


def _worker_init(benchmark_close, strategy, min_conf, min_rr, min_vol) -> None:
    _WORKER_CTX.update(
        benchmark_close=benchmark_close, strategy=strategy,
        min_conf=min_conf, min_rr=min_rr, min_vol=min_vol,
    )


def _records_for(item):
    ticker, df = item
    if df is None or df.empty or 'Close' not in df.columns:
        return []
    strategy = _WORKER_CTX['strategy']
    benchmark_close = _WORKER_CTX['benchmark_close']
    close = df['Close'].dropna()
    if len(close) < MIN_BARS + 2:
        return []
    panel = compute_feature_panel(df, benchmark_close, strategy)
    if panel is None:
        return []
    index = close.index
    bench = benchmark_close.reindex(index).ffill()
    regime_ok = bench >= sma(bench, strategy.ma_long)

    high_full = df['High'] if 'High' in df.columns else df['Close']
    low_full = df['Low'] if 'Low' in df.columns else df['Close']
    atr_series = atr(high_full, low_full, df['Close'], strategy.atr_period).shift(1)

    out = []
    cooldown_until = -1
    for pos in range(MIN_BARS, len(index) - 1):
        if pos <= cooldown_until:
            continue
        if not bool(regime_ok.iloc[pos]):
            continue
        features = features_at(panel, pos, strategy)
        if features is None or features.avg_volume < _WORKER_CTX['min_vol']:
            continue
        setup = detect_setup(features, strategy)
        if setup.setup_type != BREAKOUT:
            continue
        plan = build_trade_plan(features, setup, strategy)
        if not plan.immediate_entry or plan.entry is None or plan.stop is None:
            continue
        if plan.reward_risk is None or plan.reward_risk < _WORKER_CTX['min_rr']:
            continue
        conf = confidence_score(features, setup, plan, strategy)
        if conf < _WORKER_CTX['min_conf']:
            continue
        date = index[pos]
        high, low, fwd_close, atr_prev = _forward_arrays(
            df, date, strategy.atr_period, atr_series
        )
        if len(high) == 0:
            continue
        res = simulate_trade(
            float(plan.entry), float(plan.stop), float(plan.target),
            high, low, fwd_close, atr_prev, STRUCTURAL,
        )
        if res is None or not pd.notna(res.r_multiple):
            continue
        rec = {label: extract(features) for label, extract in PREDICTORS}
        rec['r'] = float(res.r_multiple)
        out.append(rec)
        cooldown_until = pos + 5
    return out


def _bucket_report(records: list[dict], label: str, nbuckets: int = 4) -> None:
    vals = sorted(r[label] for r in records)
    if len(set(vals)) < nbuckets:
        return
    qs = [vals[int(len(vals) * k / nbuckets)] for k in range(1, nbuckets)]
    edges = [-float('inf'), *qs, float('inf')]
    print(f'\n{label}')
    print(f"  {'bucket':<22} {'n':>5} {'meanR':>7} {'win%':>6}")
    for i in range(nbuckets):
        lo, hi = edges[i], edges[i + 1]
        sub = [r['r'] for r in records if lo <= r[label] < hi]
        if not sub:
            continue
        mean = sum(sub) / len(sub)
        win = sum(1 for x in sub if x > 0) / len(sub) * 100
        lo_s = '-inf' if lo == -float('inf') else f'{lo:.3g}'
        hi_s = 'inf' if hi == float('inf') else f'{hi:.3g}'
        print(f'  [{lo_s:>8},{hi_s:>8}) {len(sub):>5} {mean:>7.3f} {win:>5.1f}%')


def main() -> int:
    parser = argparse.ArgumentParser(description='Mine breakout-quality predictors.')
    parser.add_argument('--max-tickers', type=int, default=250)
    parser.add_argument('--period', default='10y')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--buckets', type=int, default=4)
    parser.add_argument(
        '--min-relvol', type=float, default=None,
        help='Only analyze breakouts with rel_volume >= this (conditional/independence test).',
    )
    args = parser.parse_args()

    settings = load_settings()
    cache = SQLiteCache(settings.cache_dir)
    client = YahooFinanceClient(settings=settings, cache=cache)
    strategy = StrategyConfig.from_settings(settings)

    tickers = list(load_sp500_universe(cache).tickers)
    if args.max_tickers > 0:
        tickers = tickers[:args.max_tickers]

    bench = client.fetch_history([BENCHMARK], period=args.period).get(BENCHMARK)
    if bench is None or bench.empty:
        print('Benchmark history unavailable.')
        return 1
    benchmark_close = bench['Close'].dropna()
    histories = client.fetch_history(tickers, period=args.period)

    items = [(t, histories.get(t)) for t in tickers]
    records: list[dict] = []
    init = (benchmark_close, strategy, settings.rec_min_confidence,
            settings.rec_min_reward_risk, settings.min_avg_volume)
    if args.workers > 1:
        with ProcessPoolExecutor(
            max_workers=args.workers, initializer=_worker_init, initargs=init,
        ) as pool:
            for recs in pool.map(_records_for, items):
                records.extend(recs)
    else:
        _worker_init(*init)
        for item in items:
            records.extend(_records_for(item))

    if not records:
        print('No breakout entries captured.')
        return 0

    if args.min_relvol is not None:
        records = [r for r in records if r['rel_volume (surge)'] >= args.min_relvol]
        print(f'\n[conditional] rel_volume >= {args.min_relvol:g}')
        if not records:
            print('No breakout entries in this subset.')
            return 0

    rs = [r['r'] for r in records]
    mean = sum(rs) / len(rs)
    win = sum(1 for x in rs if x > 0) / len(rs) * 100
    print(
        f'\nBreakout entries: {len(records)} | baseline ExpR {mean:.3f} | win {win:.1f}%'
    )
    for label, _ in PREDICTORS:
        _bucket_report(records, label, args.buckets)
    print('\nQuartile buckets of each feature; meanR is Structural-stop expectancy.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
