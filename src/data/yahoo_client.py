from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import yfinance as yf

from src.config import Settings
from src.data.cache import SQLiteCache
from src.data.rate_limiter import RateLimiter, exponential_backoff_sleep
from src.utils.errors import DataFetchError
from src.utils.logger import get_logger

ALLOWED_EXCHANGES = {
    'NYQ',  # NYSE
    'NMS',  # Nasdaq Global Select Market
    'ASE',  # NYSE American (AMEX)
    'PCX',  # NYSE Arca (ETFs, e.g. VTI)
    'NGM',  # Nasdaq Global Market (ETFs, e.g. VXUS)
    'NAS',  # Nasdaq mutual funds (e.g. FSELX)
    'BTS',  # Cboe BZX (e.g. CBOE; also lists some ETFs)
}


@dataclass
class Fundamentals:
    ticker: str
    company_name: str | None
    market_cap: float | None
    pe_ratio: float | None
    revenue_growth: float | None
    exchange: str | None
    quote_type: str | None = None


@dataclass
class FundHoldings:
    """Top holdings of a fund (Yahoo exposes only the top ~10)."""

    ticker: str
    holdings: dict[str, float] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    top_weight_total: float = 0.0


class YahooFinanceClient:
    def __init__(self, settings: Settings, cache: SQLiteCache) -> None:
        self.settings = settings
        self.cache = cache
        self.rate_limiter = RateLimiter(settings.request_delay_seconds)
        self.logger = get_logger(self.__class__.__name__)

    def _with_retry(self, call: Callable[[], Any], operation: str) -> Any:
        """Run ``call`` with rate limiting and exponential backoff.

        Retries up to ``settings.max_retries`` times, raising
        :class:`DataFetchError` once every attempt has failed.
        """
        attempts = max(self.settings.max_retries, 1)
        last_exc: Exception | None = None
        for attempt in range(attempts):
            self.rate_limiter.wait()
            try:
                return call()
            except Exception as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    exponential_backoff_sleep(self.settings.backoff_seconds, attempt)
        raise DataFetchError(f'{operation} failed after {attempts} attempts: {last_exc}') from last_exc

    def fetch_history(
        self,
        tickers: list[str],
        period: str = '2y',
        interval: str = '1d',
        force_refresh: bool = False,
        refresh_tickers: Iterable[str] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Fetch daily history, serving fresh data from the cache where possible.

        ``force_refresh`` bypasses the cache for every ticker. ``refresh_tickers``
        bypasses it for just that subset -- used to keep a small priority set
        (held + watchlist names) live during trading hours while the broader
        universe stays on the normal cache.
        """
        sorted_tickers = sorted(set(tickers))
        force_set = {t.upper() for t in refresh_tickers} if refresh_tickers else set()
        result: dict[str, pd.DataFrame] = {}
        missing: list[str] = []

        for ticker in sorted_tickers:
            cache_key = f'history:{ticker}:{period}:{interval}'
            if not force_refresh and ticker.upper() not in force_set:
                cached = self.cache.get(cache_key)
                if cached is not None:
                    result[ticker] = cached
                    continue
            missing.append(ticker)

        if missing:
            batch_data = self._download_batch(missing, period=period, interval=interval)
            ttl_seconds = self.settings.cache_ttl_hours * 3600
            for ticker in missing:
                cache_key = f'history:{ticker}:{period}:{interval}'
                df = batch_data.get(ticker)
                if df is not None and not df.empty:
                    result[ticker] = df
                    self.cache.set(cache_key, df, ttl_seconds=ttl_seconds)
                    continue
                # A failed (re)download falls back to any cached copy so a forced
                # refresh that gets throttled never blanks out a held name.
                cached = self.cache.get(cache_key)
                if cached is not None:
                    result[ticker] = cached

        return result

    def _download_batch(
        self, tickers: list[str], period: str = '2y', interval: str = '1d'
    ) -> dict[str, pd.DataFrame]:
        if not tickers:
            return {}

        def download():
            return yf.download(
                tickers=tickers,
                period=period,
                interval=interval,
                auto_adjust=False,
                actions=True,
                progress=False,
                threads=True,
                group_by='ticker',
            )

        try:
            data = self._with_retry(download, operation='download history')
        except DataFetchError as exc:
            self.logger.warning('History batch of %s symbols failed: %s', len(tickers), exc)
            return {}

        output: dict[str, pd.DataFrame] = {}

        if isinstance(data.columns, pd.MultiIndex):
            for ticker in tickers:
                if ticker not in data.columns.get_level_values(0):
                    output[ticker] = pd.DataFrame()
                    continue
                df = data[ticker].copy().dropna(how='all')
                output[ticker] = df
        else:
            # yfinance returns flat (non-MultiIndex) columns for a single ticker.
            ticker = tickers[0]
            output[ticker] = data.copy().dropna(how='all')

        return output

    def fetch_fundamentals(
        self, tickers: list[str], force_refresh: bool = False
    ) -> dict[str, Fundamentals]:
        output: dict[str, Fundamentals] = {}

        unique_tickers = sorted(set(tickers))
        to_fetch: list[str] = []
        for ticker in unique_tickers:
            if not force_refresh:
                cached = self.cache.get(f'fundamentals:{ticker}')
                if cached is not None:
                    output[ticker] = Fundamentals(**cached)
                    continue
            to_fetch.append(ticker)

        if not to_fetch:
            return output

        workers = max(1, min(self.settings.fundamentals_max_workers, len(to_fetch)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = executor.map(self._fetch_one_fundamental, to_fetch)

        for entry in results:
            if entry is not None:
                output[entry.ticker] = entry

        return output

    def _fetch_one_fundamental(self, ticker: str) -> Fundamentals | None:
        try:
            info = self._with_retry(
                lambda t=ticker: yf.Ticker(t).info,
                operation=f'fetch fundamentals {ticker}',
            )
        except DataFetchError as exc:
            self.logger.warning('Skipping fundamentals for %s: %s', ticker, exc)
            return None

        info = info or {}
        entry = Fundamentals(
            ticker=ticker,
            company_name=info.get('shortName') or info.get('longName'),
            market_cap=_coerce_number(info.get('marketCap')),
            pe_ratio=_coerce_number(info.get('trailingPE')),
            revenue_growth=_coerce_number(info.get('revenueGrowth')),
            exchange=info.get('exchange'),
            quote_type=info.get('quoteType'),
        )

        self.cache.set(f'fundamentals:{ticker}', entry.__dict__, ttl_seconds=self.settings.fundamentals_ttl_hours * 3600)
        return entry

    def fetch_earnings_dates(self, tickers: list[str], force_refresh: bool = False) -> dict[str, str]:
        """Next earnings date (string) per ticker; best-effort, cached, missing skipped."""
        output: dict[str, str] = {}
        for ticker in sorted(set(tickers)):
            cache_key = f'earnings:{ticker}'
            if not force_refresh:
                cached = self.cache.get(cache_key)
                if cached is not None:
                    if cached.get('date'):
                        output[ticker] = cached['date']
                    continue
            date = self._fetch_one_earnings(ticker)
            self.cache.set(cache_key, {'date': date}, ttl_seconds=self.settings.cache_ttl_hours * 3600)
            if date:
                output[ticker] = date
        return output

    def _fetch_one_earnings(self, ticker: str) -> str | None:
        try:
            cal = self._with_retry(
                lambda t=ticker: yf.Ticker(t).calendar,
                operation=f'fetch earnings {ticker}',
            )
        except DataFetchError as exc:
            self.logger.warning('Skipping earnings for %s: %s', ticker, exc)
            return None
        if not cal:
            return None
        dates = cal.get('Earnings Date') if isinstance(cal, dict) else None
        if not dates:
            return None
        first = dates[0] if isinstance(dates, (list, tuple)) else dates
        return str(first)

    def filter_allowed_exchanges(
        self, fundamentals: dict[str, Fundamentals]
    ) -> tuple[list[str], list[str]]:
        included: list[str] = []
        excluded: list[str] = []

        for ticker, item in fundamentals.items():
            if not item.exchange:
                # Unknown exchange: keep the symbol rather than drop it.
                included.append(ticker)
                continue

            if item.exchange in ALLOWED_EXCHANGES:
                included.append(ticker)
            else:
                excluded.append(ticker)

        if excluded:
            self.logger.warning('Excluded %s symbols outside allowed exchanges', len(excluded))

        return included, excluded

    def fetch_fund_holdings(
        self, tickers: list[str], force_refresh: bool = False
    ) -> dict[str, FundHoldings]:
        """Top-holdings look-through for each fund ticker (cached)."""
        output: dict[str, FundHoldings] = {}
        for ticker in sorted(set(tickers)):
            cache_key = f'fund_holdings:{ticker}'
            if not force_refresh:
                cached = self.cache.get(cache_key)
                if cached is not None:
                    output[ticker] = FundHoldings(**cached)
                    continue
            entry = self._fetch_one_fund_holdings(ticker)
            if entry is not None and entry.holdings:
                output[ticker] = entry
                self.cache.set(
                    cache_key, entry.__dict__, ttl_seconds=self.settings.cache_ttl_hours * 3600
                )
        return output

    def _fetch_one_fund_holdings(self, ticker: str) -> FundHoldings | None:
        try:
            top = self._with_retry(
                lambda t=ticker: yf.Ticker(t).funds_data.top_holdings,
                operation=f'fetch fund holdings {ticker}',
            )
        except DataFetchError as exc:
            self.logger.warning('Skipping fund holdings for %s: %s', ticker, exc)
            return None

        if top is None or getattr(top, 'empty', True):
            return None

        holdings: dict[str, float] = {}
        names: dict[str, str] = {}
        for symbol, row in top.iterrows():
            pct = _coerce_number(row.get('Holding Percent'))
            if pct is None:
                continue
            sym = str(symbol)
            holdings[sym] = float(pct)
            name = row.get('Name')
            if name is not None:
                names[sym] = str(name)

        if not holdings:
            return None
        return FundHoldings(
            ticker=ticker,
            holdings=holdings,
            names=names,
            top_weight_total=sum(holdings.values()),
        )


def _coerce_number(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number
