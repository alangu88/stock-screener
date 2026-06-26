from __future__ import annotations

from dataclasses import dataclass
from io import StringIO

import pandas as pd
import requests

from src.data.cache import SQLiteCache
from src.utils.errors import UniverseLoadError

SP500_WIKI_URL = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
SP500_FALLBACK_CSV_URL = 'https://datahub.io/core/s-and-p-500-companies/r/constituents.csv'
REQUEST_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/126.0.0.0 Safari/537.36'
    )
}
CACHE_KEY = 'sp500_universe_v1'
CACHE_TTL_SECONDS = 7 * 24 * 3600


@dataclass
class UniverseResult:
    tickers: list[str]
    companies: dict[str, str]


def normalize_ticker(symbol: str) -> str:
    return symbol.replace('.', '-').strip().upper()


def load_sp500_universe(cache: SQLiteCache, force_refresh: bool = False) -> UniverseResult:
    if not force_refresh:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return UniverseResult(tickers=cached['tickers'], companies=cached['companies'])

    # Wikipedia is the source of truth; the datahub CSV is a fallback for when
    # Wikipedia blocks the request or changes its table layout.
    errors: list[str] = []
    for source in (_load_from_wikipedia, _load_from_fallback_csv):
        try:
            symbols, names = source()
        except (requests.RequestException, ValueError, KeyError, UniverseLoadError) as exc:  # pragma: no cover - network path
            errors.append(f'{source.__name__}: {exc}')
            continue
        if symbols and names:
            return _store_universe(cache, symbols, names)

    raise UniverseLoadError('Unable to load S&P 500 universe. ' + ' | '.join(errors))


def _store_universe(cache: SQLiteCache, symbols: list[str], names: list[str]) -> UniverseResult:
    if len(symbols) != len(names):
        raise UniverseLoadError(
            f'Symbol/name length mismatch: {len(symbols)} symbols vs {len(names)} names'
        )
    tickers = [normalize_ticker(s) for s in symbols]
    companies = {normalize_ticker(s): n for s, n in zip(symbols, names, strict=True)}
    cache.set(CACHE_KEY, {'tickers': tickers, 'companies': companies}, ttl_seconds=CACHE_TTL_SECONDS)
    return UniverseResult(tickers=tickers, companies=companies)


def _load_from_wikipedia() -> tuple[list[str], list[str]]:
    response = requests.get(SP500_WIKI_URL, headers=REQUEST_HEADERS, timeout=20)
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    if not tables:
        raise UniverseLoadError('No tables found in Wikipedia HTML')

    df = tables[0]
    symbols = df['Symbol'].astype(str).tolist()
    names = df['Security'].astype(str).tolist()
    return symbols, names


def _load_from_fallback_csv() -> tuple[list[str], list[str]]:
    response = requests.get(SP500_FALLBACK_CSV_URL, headers=REQUEST_HEADERS, timeout=20)
    response.raise_for_status()
    df = pd.read_csv(StringIO(response.text))

    if 'Symbol' not in df.columns or 'Name' not in df.columns:
        raise UniverseLoadError('Fallback CSV schema missing Symbol/Name columns')

    symbols = df['Symbol'].astype(str).tolist()
    names = df['Name'].astype(str).tolist()
    return symbols, names
