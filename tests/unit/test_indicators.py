import pandas as pd

from src.analysis.indicators import ema, rsi, sma


def test_sma_rolling_mean():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = sma(s, 3)
    assert round(float(out.iloc[-1]), 6) == 4.0


def test_ema_returns_value_after_min_periods():
    s = pd.Series([10, 11, 12, 13, 14, 15], dtype=float)
    out = ema(s, 3)
    assert out.notna().sum() >= 3


def test_rsi_stays_bounded():
    s = pd.Series([100, 101, 102, 99, 98, 100, 105, 107, 104, 103], dtype=float)
    out = rsi(s, 5)
    valid = out.dropna()
    assert ((valid >= 0) & (valid <= 100)).all()


def test_sma_over_volume_window():
    s = pd.Series([100, 200, 300, 400, 500], dtype=float)
    out = sma(s, 2)
    assert float(out.iloc[-1]) == 450.0
