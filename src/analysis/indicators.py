from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    return rsi_series.fillna(50)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range (Wilder's smoothing)."""
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def rolling_high(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).max()


def rolling_low(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).min()


def on_balance_volume(close: pd.Series, volume: pd.Series) -> pd.Series:
    """Cumulative volume signed by daily price direction (Granville's OBV)."""
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).cumsum()


def slope_pct(series: pd.Series, lookback: int) -> float:
    """Fractional change of a series over ``lookback`` bars (a simple slope)."""
    clean = series.dropna()
    if len(clean) <= lookback:
        return 0.0
    past = float(clean.iloc[-1 - lookback])
    latest = float(clean.iloc[-1])
    if past == 0:
        return 0.0
    return latest / past - 1.0


def compute_indicators(
    df: pd.DataFrame,
    *,
    rsi_period: int = 14,
    volume_window: int = 50,
    sma_windows: tuple[int, ...] = (50, 200),
    ema_windows: tuple[int, ...] = (20,),
) -> pd.DataFrame:
    """Return a Close/Volume frame enriched with indicator columns.

    Expects ``df`` to contain at least ``Close`` and ``Volume`` columns.
    Output columns use the convention ``SMA<window>``, ``EMA<window>``,
    ``RSI`` and ``VOL_AVG``.
    """
    close = df['Close'].dropna()
    volume = df['Volume'].dropna()

    out = pd.DataFrame(index=close.index)
    out['Close'] = close
    out['Volume'] = volume.reindex(out.index)
    for window in sma_windows:
        out[f'SMA{window}'] = sma(out['Close'], window)
    for window in ema_windows:
        out[f'EMA{window}'] = ema(out['Close'], window)
    out['RSI'] = rsi(out['Close'], rsi_period)
    out['VOL_AVG'] = sma(out['Volume'], volume_window)
    return out
