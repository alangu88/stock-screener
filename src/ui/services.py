"""Cached construction of the long-lived service objects.

``get_services`` is memoized with ``st.cache_resource`` so the engine, client,
and cache survive Streamlit reruns instead of being rebuilt on every interaction.
"""

from __future__ import annotations

import streamlit as st

from src.config import Settings, load_settings
from src.data.cache import SQLiteCache
from src.data.yahoo_client import YahooFinanceClient
from src.screener.engine import ScreenerEngine
from src.screener.strategy import StrategyConfig


@st.cache_resource
def get_services() -> tuple[Settings, SQLiteCache, YahooFinanceClient, ScreenerEngine]:
    settings = load_settings()
    cache = SQLiteCache(settings.cache_dir)
    client = YahooFinanceClient(settings=settings, cache=cache)
    engine = ScreenerEngine(
        client=client,
        strategy=StrategyConfig.from_settings(settings),
    )
    return settings, cache, client, engine
