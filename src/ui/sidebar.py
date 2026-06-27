"""Sidebar controls: cache status, screen gates, and portfolio construction."""

from __future__ import annotations

from dataclasses import dataclass, replace

import streamlit as st

from src.config import Settings
from src.data.cache import SQLiteCache
from src.screener.engine import FilterConfig
from src.screener.portfolio import PortfolioConfig
from src.screener.setups import BREAKOUT, CONTRACTION, PULLBACK

SETUP_OPTIONS = (BREAKOUT, CONTRACTION, PULLBACK)


@dataclass
class ViewOptions:
    rsi_period: int


def render_cache_controls(cache: SQLiteCache) -> None:
    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button('Refresh Cached Data'):
            cache.clear()
            st.success('Cache cleared. New requests will pull fresh data.')
    with col_b:
        stats = cache.stats()
        st.info(f"Cache entries: {stats['live']} live / {stats['total']} total")


def render_sidebar(settings: Settings) -> tuple[FilterConfig, PortfolioConfig, ViewOptions]:
    st.sidebar.header('Screen Controls')
    min_confidence = st.sidebar.slider(
        'Min Confidence', min_value=0, max_value=100, value=45,
        help='Composite quality score for the setup (trend, RS, base, volume, reward).',
    )
    min_reward_risk = st.sidebar.slider(
        'Min Reward/Risk', min_value=1.0, max_value=5.0, value=1.5, step=0.1,
        help='Only keep setups whose target offers at least this multiple of the risk. '
             'Contractions run ~1.8R; pullbacks/breakouts project the full base move.',
    )
    min_volume = st.sidebar.number_input(
        'Min Average Volume', min_value=0, step=50_000, value=settings.min_avg_volume
    )
    selected_setups = st.sidebar.multiselect(
        'Setup Types', options=list(SETUP_OPTIONS), default=list(SETUP_OPTIONS)
    )
    rsi_period = st.sidebar.slider('Chart RSI Period', min_value=5, max_value=30, value=settings.rsi_period)

    st.sidebar.header('Portfolio')
    core_allocation = st.sidebar.slider(
        'Core Allocation', min_value=0.0, max_value=1.0, value=float(settings.core_allocation), step=0.05,
        help='Share of capital for the Core sleeve (durable trend-continuation leaders). '
             'The remainder funds the higher-octane Satellite sleeve.',
    )
    core_threshold = st.sidebar.slider(
        'Core Score Threshold', min_value=0.0, max_value=1.0, value=float(settings.core_score_threshold), step=0.05,
        help='Core-ness score at or above which a candidate joins the Core sleeve.',
    )
    max_position_weight = st.sidebar.slider(
        'Max Position Weight', min_value=0.02, max_value=0.25, value=float(settings.max_position_weight), step=0.01,
        help='Cap on any single name as a share of the whole book.',
    )

    setups = tuple(selected_setups) if selected_setups else None
    config = replace(
        FilterConfig.from_settings(settings),
        min_confidence=float(min_confidence),
        min_reward_risk=float(min_reward_risk),
        min_avg_volume=int(min_volume),
        setups=setups,
    )
    portfolio = replace(
        PortfolioConfig.from_settings(settings),
        core_allocation=float(core_allocation),
        satellite_allocation=round(1.0 - float(core_allocation), 4),
        core_score_threshold=float(core_threshold),
        max_position_weight=float(max_position_weight),
    )
    view = ViewOptions(rsi_period=int(rsi_period))
    return config, portfolio, view
