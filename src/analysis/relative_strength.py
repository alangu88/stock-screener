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


def rs_line_at_high(
    stock_close: pd.Series, benchmark_close: pd.Series, window: int, tolerance: float = 0.0
) -> bool:
    """True when the stock/benchmark ratio line is at (or near) a window high.

    A relative-strength line making new highs is one of the earliest tells of
    institutional leadership and often precedes price breakouts.
    """
    aligned = pd.concat([stock_close, benchmark_close], axis=1, join='inner').dropna()
    if len(aligned) < 2:
        return False
    ratio = aligned.iloc[:, 0] / aligned.iloc[:, 1]
    window_high = ratio.rolling(window=window, min_periods=1).max().iloc[-1]
    if window_high == 0:
        return False
    return bool(ratio.iloc[-1] >= window_high * (1 - tolerance))
