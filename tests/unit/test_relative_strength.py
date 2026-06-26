import pandas as pd

from src.analysis.relative_strength import outperformance_vs_benchmark


def test_outperformance_positive_when_stock_beats_spy():
    stock = pd.Series([100, 102, 104, 108], dtype=float)
    spy = pd.Series([100, 101, 102, 103], dtype=float)
    result = outperformance_vs_benchmark(stock, spy, lookback_days=3)
    assert result > 0
