from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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

# Yahoo throttles large bulk downloads and silently drops a random subset, so
# history is fetched in chunks of this size, with dropped names retried
# individually afterward (see ``_download_with_recovery``).
HISTORY_CHUNK_SIZE = 50


@dataclass
class Fundamentals:
    ticker: str
    company_name: str | None
    market_cap: float | None
    pe_ratio: float | None
    revenue_growth: float | None
    exchange: str | None
    quote_type: str | None = None
    dividend_yield: float | None = None  # fraction (0.02 = 2%)
    sector: str | None = None


def _dividend_yield(info: dict[str, Any]) -> float | None:
    """Dividend yield as a fraction (0.02 = 2%).

    Yahoo's ``trailingAnnualDividendYield`` is already a fraction; the legacy
    ``dividendYield`` field is a percent number, so scale it down as a fallback.
    """
    frac = _coerce_number(info.get('trailingAnnualDividendYield'))
    if frac is not None:
        return frac
    pct = _coerce_number(info.get('dividendYield'))
    return pct / 100.0 if pct is not None else None


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
            batch_data = self._download_with_recovery(missing, period=period, interval=interval)
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

    def fetch_history_live(
        self,
        tickers: list[str],
        period: str = '2y',
        interval: str = '1d',
        tail_period: str = '5d',
    ) -> dict[str, pd.DataFrame]:
        """Serve the full ``period`` window from cache, refreshing only the tail.

        The bulky long window is reused from the cache and never re-downloaded;
        only the most recent ``tail_period`` bars are pulled and spliced on top.
        That keeps same-day reruns cheap and captures a fresh latest price at run
        time without the rate-limit failures a full long-window refresh of the
        whole universe tends to trigger. Names that a throttled batch drops are
        retried individually so their price still refreshes; a download that still
        fails keeps the cached copy rather than blanking the name.
        """
        sorted_tickers = sorted(set(tickers))
        result = self.fetch_history(sorted_tickers, period=period, interval=interval)
        tail = self._download_with_recovery(sorted_tickers, period=tail_period, interval=interval)
        ttl_seconds = self.settings.cache_ttl_hours * 3600
        for ticker in sorted_tickers:
            recent = tail.get(ticker)
            if recent is None or recent.empty:
                continue
            base = result.get(ticker)
            merged = recent if base is None or base.empty else self._splice_tail(base, recent)
            result[ticker] = merged
            self.cache.set(f'history:{ticker}:{period}:{interval}', merged, ttl_seconds=ttl_seconds)
        return result

    @staticmethod
    def _splice_tail(base: pd.DataFrame, recent: pd.DataFrame) -> pd.DataFrame:
        """Overlay fresh ``recent`` bars onto ``base``, replacing same-dated rows."""
        combined = pd.concat([base, recent])
        combined = combined[~combined.index.duplicated(keep='last')]
        return combined.sort_index()

    def _download_with_recovery(
        self, tickers: list[str], period: str = '2y', interval: str = '1d'
    ) -> dict[str, pd.DataFrame]:
        """Download history in throttle-resistant chunks, recovering dropped names.

        A single large ``yf.download`` gets throttled by Yahoo, which then silently
        returns an empty frame for a random subset of the batch. Fetching in
        smaller chunks cuts that truncation, and any name still missing after its
        chunk is retried individually -- single-ticker downloads are far more
        reliable -- so a throttled run does not lose live symbols to a false
        "possibly delisted".
        """
        unique = list(dict.fromkeys(tickers))
        result: dict[str, pd.DataFrame] = {}
        for start in range(0, len(unique), HISTORY_CHUNK_SIZE):
            chunk = unique[start:start + HISTORY_CHUNK_SIZE]
            batch = self._download_batch(chunk, period=period, interval=interval)
            for ticker in chunk:
                df = batch.get(ticker)
                if df is not None and not df.empty:
                    result[ticker] = df
        for ticker in [t for t in unique if t not in result]:
            retry = self._download_batch([ticker], period=period, interval=interval)
            df = retry.get(ticker)
            if df is not None and not df.empty:
                result[ticker] = df
        still_missing = [t for t in unique if t not in result]
        if still_missing:
            preview = ', '.join(still_missing[:10]) + ('...' if len(still_missing) > 10 else '')
            self.logger.warning(
                '%s/%s symbols unavailable after retry (throttled or delisted): %s',
                len(still_missing), len(unique), preview,
            )
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

    def _fetch_missing_parallel(
        self,
        tickers: list[str],
        cache_key: Callable[[str], str],
        from_cache: Callable[[Any], Any | None],
        fetch_one: Callable[[str], Any | None],
        force_refresh: bool,
    ) -> dict[str, Any]:
        """Serve cache hits, then fetch the misses across a thread pool.

        ``fetch_one`` performs one Yahoo round-trip for a single ticker and owns
        its own cache write, so each fetcher keeps its own positive/negative
        cache policy. Concurrency is bounded by ``fundamentals_max_workers`` --
        the shared limit for all per-ticker Yahoo ``.info`` lookups.
        """
        output: dict[str, Any] = {}
        to_fetch: list[str] = []
        for ticker in sorted(set(tickers)):
            if not force_refresh:
                cached = self.cache.get(cache_key(ticker))
                if cached is not None:
                    try:
                        result = from_cache(cached)
                    except (TypeError, KeyError, ValueError, AttributeError) as exc:
                        # A cache entry whose schema drifted (field added/removed)
                        # is dropped and refetched rather than allowed to abort
                        # the whole batch.
                        self.logger.warning('Discarding unreadable cache for %s: %s', ticker, exc)
                    else:
                        if result is not None:
                            output[ticker] = result
                        continue  # valid hit, including a negative-cached miss
            to_fetch.append(ticker)

        if not to_fetch:
            return output

        workers = max(1, min(self.settings.fundamentals_max_workers, len(to_fetch)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_ticker = {executor.submit(fetch_one, ticker): ticker for ticker in to_fetch}
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    result = future.result()
                except Exception as exc:
                    # One ticker's unexpected failure must not lose the batch.
                    self.logger.warning('Fetch failed for %s: %s', ticker, exc)
                    continue
                if result is not None:
                    output[ticker] = result
        return output

    def fetch_fundamentals(
        self, tickers: list[str], force_refresh: bool = False
    ) -> dict[str, Fundamentals]:
        return self._fetch_missing_parallel(
            tickers,
            cache_key=lambda t: f'fundamentals:{t}',
            from_cache=lambda cached: Fundamentals(**cached),
            fetch_one=self._fetch_one_fundamental,
            force_refresh=force_refresh,
        )

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
            dividend_yield=_dividend_yield(info),
            sector=info.get('sector'),
        )

        self.cache.set(f'fundamentals:{ticker}', entry.__dict__, ttl_seconds=self.settings.fundamentals_ttl_hours * 3600)
        return entry

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


def _coerce_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number
