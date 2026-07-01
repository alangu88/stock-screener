import pandas as pd

from src.analysis.features import MIN_BARS, compute_features
from src.screener.strategy import StrategyConfig

CONFIG = StrategyConfig()


def _uptrend_frame(periods: int = 260) -> pd.DataFrame:
    idx = pd.date_range('2024-01-01', periods=periods, freq='B')
    close = pd.Series([50.0 + i for i in range(periods)], index=idx)
    return pd.DataFrame(
        {
            'Open': close - 0.5,
            'High': close + 1.0,
            'Low': close - 1.0,
            'Close': close,
            'Volume': pd.Series([1_000_000.0] * periods, index=idx),
        },
        index=idx,
    )


def _benchmark(periods: int = 260) -> pd.Series:
    idx = pd.date_range('2024-01-01', periods=periods, freq='B')
    return pd.Series([100.0 + i * 0.2 for i in range(periods)], index=idx)


def test_uptrend_features_are_bullish():
    features = compute_features(_uptrend_frame(), _benchmark(), CONFIG)
    assert features is not None
    assert features.stacked is True
    assert features.trend_score >= 0.7
    assert features.rs_outperformance > 0
    assert features.pct_from_high <= 0
    assert features.ma_long_slope > 0


def test_close_only_feed_does_not_raise():
    idx = pd.date_range('2024-01-01', periods=260, freq='B')
    close = pd.Series([50.0 + i for i in range(260)], index=idx)
    df = pd.DataFrame({'Close': close, 'Volume': pd.Series([900_000.0] * 260, index=idx)}, index=idx)
    features = compute_features(df, _benchmark(), CONFIG)
    assert features is not None
    assert features.atr >= 0


def test_insufficient_history_returns_none():
    assert compute_features(_uptrend_frame(MIN_BARS - 1), _benchmark(MIN_BARS - 1), CONFIG) is None


def test_missing_columns_returns_none():
    df = pd.DataFrame({'Open': [1, 2, 3]})
    assert compute_features(df, _benchmark(), CONFIG) is None

