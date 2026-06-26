"""Generate the daily screener snapshot and write it into the README.

Headless entry point for CI (GitHub Actions) and local runs. It screens a capped
slice of the S&P 500, renders a Markdown block, and replaces the marked region in
README.md. Network failures (e.g. Yahoo throttling CI IPs) are caught and turned
into an "unavailable" notice so the README is never left half-written.

Run from the repo root:
    python scripts/generate_snapshot.py
    SCREENER_SNAPSHOT_SYMBOLS=30 python scripts/generate_snapshot.py
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.config import load_settings  # noqa: E402
from src.data.cache import SQLiteCache  # noqa: E402
from src.data.universe import UniverseResult, load_sp500_universe  # noqa: E402
from src.data.yahoo_client import YahooFinanceClient  # noqa: E402
from src.export.markdown_export import (  # noqa: E402
    build_snapshot_markdown,
    build_unavailable_markdown,
    inject_between_markers,
)
from src.screener.engine import FilterConfig, ScreenerEngine  # noqa: E402
from src.screener.portfolio import PortfolioConfig  # noqa: E402
from src.screener.strategy import StrategyConfig  # noqa: E402

README_PATH = _REPO_ROOT / 'README.md'
DEFAULT_SYMBOLS = 0  # 0 (or unset) => screen the entire S&P 500 universe
DEFAULT_LIMIT = 20


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _trim_universe(universe: UniverseResult, max_symbols: int) -> UniverseResult:
    if max_symbols <= 0 or max_symbols >= len(universe.tickers):
        return universe  # screen everything
    tickers = universe.tickers[:max_symbols]
    companies = {t: universe.companies.get(t, '') for t in tickers}
    return UniverseResult(tickers=tickers, companies=companies)


def _regime_label(df) -> str:
    if 'Market Context' in df.columns and not df.empty:
        value = df['Market Context'].iloc[0]
        if value:
            return str(value)
    return 'Unknown'


def main() -> int:
    settings = load_settings()
    max_symbols = _env_int('SCREENER_SNAPSHOT_SYMBOLS', DEFAULT_SYMBOLS)
    limit = max(1, _env_int('SCREENER_SNAPSHOT_LIMIT', DEFAULT_LIMIT))
    generated_at = datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')

    cache = SQLiteCache(settings.cache_dir)
    client = YahooFinanceClient(settings=settings, cache=cache)
    engine = ScreenerEngine(
        client=client,
        strategy=StrategyConfig.from_settings(settings),
        portfolio=PortfolioConfig.from_settings(settings),
    )

    try:
        universe = _trim_universe(load_sp500_universe(cache), max_symbols)
        screened = len(universe.tickers)
        df = engine.screen(universe, config=FilterConfig.from_settings(settings))
        block = build_snapshot_markdown(
            df,
            generated_at=generated_at,
            regime_label=_regime_label(df),
            symbols_screened=screened,
            limit=limit,
        )
        print(f'Screened {screened} symbols -> {len(df)} matches.')
    except Exception as exc:  # network / data feed problems must not break the README
        block = build_unavailable_markdown(generated_at=generated_at, reason=type(exc).__name__)
        print(f'Snapshot unavailable: {type(exc).__name__}: {exc}', file=sys.stderr)

    readme = README_PATH.read_text(encoding='utf-8')
    updated = inject_between_markers(readme, block)
    if updated != readme:
        README_PATH.write_text(updated, encoding='utf-8')
        print('README updated.')
    else:
        print('README unchanged.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
