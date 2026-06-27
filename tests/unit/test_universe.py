from __future__ import annotations

import pytest

from src.data import universe
from src.data.cache import SQLiteCache
from src.data.universe import (
    UniverseResult,
    load_sp500_universe,
    normalize_ticker,
)
from src.utils.errors import UniverseLoadError


@pytest.fixture
def cache(tmp_path) -> SQLiteCache:
    return SQLiteCache(tmp_path)


@pytest.mark.parametrize(
    'raw, expected',
    [
        ('aapl', 'AAPL'),
        ('BRK.B', 'BRK-B'),
        (' msft ', 'MSFT'),
        ('BF.B', 'BF-B'),
    ],
)
def test_normalize_ticker(raw: str, expected: str) -> None:
    assert normalize_ticker(raw) == expected


def test_store_universe_rejects_length_mismatch(cache: SQLiteCache) -> None:
    with pytest.raises(UniverseLoadError):
        universe._store_universe(cache, ['AAPL', 'MSFT'], ['Apple Inc.'])


def test_store_universe_normalizes_and_caches(cache: SQLiteCache) -> None:
    result = universe._store_universe(cache, ['BRK.B'], ['Berkshire Hathaway'])
    assert result.tickers == ['BRK-B']
    assert result.companies == {'BRK-B': 'Berkshire Hathaway'}
    cached = cache.get(universe.CACHE_KEY)
    assert cached['tickers'] == ['BRK-B']


def test_load_returns_cached_without_network(cache: SQLiteCache, monkeypatch) -> None:
    cache.set(
        universe.CACHE_KEY,
        {'tickers': ['AAPL'], 'companies': {'AAPL': 'Apple Inc.'}},
        ttl_seconds=3600,
    )

    def _boom() -> tuple[list[str], list[str]]:
        raise AssertionError('network should not be hit when cache is warm')

    monkeypatch.setattr(universe, '_load_from_wikipedia', _boom)
    monkeypatch.setattr(universe, '_load_from_fallback_csv', _boom)

    result = load_sp500_universe(cache)
    assert isinstance(result, UniverseResult)
    assert result.tickers == ['AAPL']


def test_load_falls_back_to_secondary_source(cache: SQLiteCache, monkeypatch) -> None:
    def _fail() -> tuple[list[str], list[str]]:
        raise UniverseLoadError('primary down')

    def _ok() -> tuple[list[str], list[str]]:
        return ['MSFT'], ['Microsoft']

    monkeypatch.setattr(universe, '_load_from_wikipedia', _fail)
    monkeypatch.setattr(universe, '_load_from_fallback_csv', _ok)

    result = load_sp500_universe(cache, force_refresh=True)
    assert result.tickers == ['MSFT']


def test_load_raises_when_all_sources_fail(cache: SQLiteCache, monkeypatch) -> None:
    def _fail() -> tuple[list[str], list[str]]:
        raise UniverseLoadError('down')

    monkeypatch.setattr(universe, '_load_from_wikipedia', _fail)
    monkeypatch.setattr(universe, '_load_from_fallback_csv', _fail)

    with pytest.raises(UniverseLoadError):
        load_sp500_universe(cache, force_refresh=True)
