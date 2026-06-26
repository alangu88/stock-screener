"""Shared deterministic ``MarketFeatures`` factory for unit tests."""

from src.analysis.features import MarketFeatures


def make_features(**overrides) -> MarketFeatures:
    base = dict(
        price=100.0,
        ma_fast=95.0,
        ma_mid=90.0,
        ma_long=85.0,
        ema_trend=96.0,
        ma_long_slope=0.05,
        ma_mid_slope=0.05,
        stacked=True,
        trend_score=0.9,
        high_52w=110.0,
        low_52w=60.0,
        pct_from_high=-0.09,
        pct_above_low=0.67,
        rs_outperformance=0.10,
        rs_line_new_high=True,
        pivot=100.0,
        recent_high=99.0,
        pivot_low=96.0,
        base_high=104.0,
        base_low=90.0,
        base_depth=0.135,
        atr=1.0,
        atr_pct=0.01,
        contraction_ratio=0.80,
        avg_volume=1_000_000.0,
        rel_volume=1.0,
        updown_volume_ratio=1.5,
        obv_slope=0.05,
    )
    base.update(overrides)
    return MarketFeatures(**base)
