from __future__ import annotations

import pandas as pd

from src.config import Settings
from src.data import yahoo_client as yc
from src.data.cache import SQLiteCache
from src.data.yahoo_client import YahooFinanceClient


def _df(price: float) -> pd.DataFrame:
    return pd.DataFrame({'Close': [price]})


def _client(tmp_path, prices, calls):
    client = YahooFinanceClient(Settings(), SQLiteCache(tmp_path))

    def fake_batch(tickers, period='2y', interval='1d'):
        calls.append(sorted(tickers))
        return {t: _df(prices[t]) for t in tickers}

    client._download_batch = fake_batch  # type: ignore[assignment]
    return client


def test_second_fetch_served_from_cache(tmp_path):
    calls: list[list[str]] = []
    prices = {'AAA': 1.0, 'BBB': 1.0}
    client = _client(tmp_path, prices, calls)
    client.fetch_history(['AAA', 'BBB'])
    prices.update({'AAA': 9.0, 'BBB': 9.0})
    out = client.fetch_history(['AAA', 'BBB'])
    assert float(out['AAA']['Close'].iloc[-1]) == 1.0
    assert len(calls) == 1  # nothing re-downloaded


def test_refresh_tickers_bypasses_cache_for_subset(tmp_path):
    calls: list[list[str]] = []
    prices = {'AAA': 1.0, 'BBB': 1.0}
    client = _client(tmp_path, prices, calls)
    client.fetch_history(['AAA', 'BBB'])
    prices.update({'AAA': 2.0, 'BBB': 2.0})
    out = client.fetch_history(['AAA', 'BBB'], refresh_tickers=['BBB'])
    assert float(out['AAA']['Close'].iloc[-1]) == 1.0  # cached
    assert float(out['BBB']['Close'].iloc[-1]) == 2.0  # refreshed
    assert calls[-1] == ['BBB']  # only the subset re-downloaded


def test_force_refresh_redownloads_all(tmp_path):
    calls: list[list[str]] = []
    prices = {'AAA': 1.0, 'BBB': 1.0}
    client = _client(tmp_path, prices, calls)
    client.fetch_history(['AAA', 'BBB'])
    prices.update({'AAA': 3.0, 'BBB': 3.0})
    out = client.fetch_history(['AAA', 'BBB'], force_refresh=True)
    assert float(out['AAA']['Close'].iloc[-1]) == 3.0
    assert calls[-1] == ['AAA', 'BBB']


def test_failed_refresh_falls_back_to_cache(tmp_path):
    """A forced refresh that fails (e.g. throttled) keeps the stale cached copy."""
    calls: list[list[str]] = []
    prices = {'AAA': 1.0}
    client = _client(tmp_path, prices, calls)
    client.fetch_history(['AAA'])  # seed the cache

    # Simulate a throttled download: the batch returns nothing.
    client._download_batch = lambda tickers, period='2y', interval='1d': {}  # type: ignore[assignment]
    out = client.fetch_history(['AAA'], refresh_tickers=['AAA'])
    assert float(out['AAA']['Close'].iloc[-1]) == 1.0  # served stale, not dropped


def test_fundamentals_cached_with_separate_long_ttl(monkeypatch):
    """Fundamentals must persist on their own (longer) TTL, not the price TTL."""
    captured: dict[str, int] = {}

    class _FakeCache:
        def get(self, key):
            return None

        def set(self, key, value, ttl_seconds):
            captured['ttl'] = ttl_seconds

    class _FakeTicker:
        def __init__(self, ticker):
            self._ticker = ticker

        @property
        def info(self):
            return {'shortName': 'X', 'exchange': 'NMS', 'quoteType': 'EQUITY'}

    monkeypatch.setattr(yc.yf, 'Ticker', _FakeTicker)
    settings = Settings(cache_ttl_hours=1, fundamentals_ttl_hours=24, request_delay_seconds=0.0)
    client = YahooFinanceClient(settings, _FakeCache())
    client.fetch_fundamentals(['AAA'])
    assert captured['ttl'] == 24 * 3600
