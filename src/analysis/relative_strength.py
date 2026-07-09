from __future__ import annotations

import pandas as pd


def total_return(close: pd.Series, lookback_days: int) -> float:
    if close.empty:
        return 0.0
    if len(close) <= lookback_days:
        base = close.iloc[0]
    else:
        base = close.iloc[-(lookback_days + 1)]
    if base == 0:
        return 0.0
    return float((close.iloc[-1] / base) - 1)


def outperformance_vs_benchmark(
    stock_close: pd.Series, benchmark_close: pd.Series, lookback_days: int
) -> float:
    return total_return(stock_close, lookback_days) - total_return(
        benchmark_close, lookback_days
    )


def blended_outperformance(
    stock_close: pd.Series,
    benchmark_close: pd.Series,
    lookbacks: tuple[int, ...],
    weights: tuple[float, ...],
) -> float:
    """Weighted multi-horizon outperformance vs the benchmark.

    Emphasising several horizons (e.g. 1/3/6 months) follows the CAN SLIM RS
    rating idea: recent strength matters most, but it should persist.
    """
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    score = 0.0
    for lookback, weight in zip(lookbacks, weights, strict=True):
        score += weight * outperformance_vs_benchmark(stock_close, benchmark_close, lookback)
    return float(score / total_weight)


def beta(stock_close: pd.Series, benchmark_close: pd.Series, lookback: int = 252) -> float:
    """CAPM beta: slope of the stock's daily returns regressed on the benchmark's.

    Uses up to ``lookback`` overlapping daily returns. Returns 1.0 (market beta)
    when there is too little overlapping history to estimate it.
    """
    aligned = pd.concat([stock_close, benchmark_close], axis=1, join='inner').dropna()
    stock_ret = aligned.iloc[:, 0].pct_change()
    bench_ret = aligned.iloc[:, 1].pct_change()
    paired = pd.concat([stock_ret, bench_ret], axis=1).dropna().tail(lookback)
    if len(paired) < 30:
        return 1.0
    bench_var = float(paired.iloc[:, 1].var())
    if bench_var == 0:
        return 1.0
    return float(paired.iloc[:, 0].cov(paired.iloc[:, 1]) / bench_var)
