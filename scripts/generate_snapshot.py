"""Generate the daily screener snapshot and write it into the README.

Headless entry point for CI (GitHub Actions) and local runs. It builds the
watchlist (your holdings plus followed names), screens the S&P 500 for fresh
high-conviction adds, renders a Markdown block, and replaces the marked region
in README.md. Network failures (e.g. Yahoo throttling CI IPs) are caught and
turned into an "unavailable" notice so the README is never left half-written.

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
from src.data.universe import (  # noqa: E402
    UniverseResult,
    load_sp500_universe,
    normalize_ticker,
)
from src.data.yahoo_client import YahooFinanceClient  # noqa: E402
from src.export.markdown_export import (  # noqa: E402
    build_snapshot_markdown,
    build_unavailable_markdown,
    inject_between_markers,
)
from src.screener.engine import FilterConfig, ScreenerEngine  # noqa: E402
from src.screener.holdings import (  # noqa: E402
    merge_holdings,
    parse_portfolio,
    parse_positions,
)
from src.screener.portfolio import PortfolioConfig  # noqa: E402
from src.screener.strategy import StrategyConfig  # noqa: E402
from src.utils.files import read_text_or_empty  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

README_PATH = _REPO_ROOT / 'README.md'
WATCHLIST_PATH = _REPO_ROOT / 'watchlist.txt'
PORTFOLIO_PATH = _REPO_ROOT / 'portfolio.txt'
POSITIONS_PATH = _REPO_ROOT / 'positions.txt'
DEFAULT_SYMBOLS = 0  # 0 (or unset) => screen the entire S&P 500 universe
DEFAULT_LIMIT = 20
_LOGGER = get_logger('generate_snapshot')


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _held_tickers() -> set[str]:
    """Tickers already held (committed composition merged with private sizes)."""
    portfolio_entries = parse_portfolio(read_text_or_empty(PORTFOLIO_PATH))
    position_entries = parse_positions(read_text_or_empty(POSITIONS_PATH))
    merged = merge_holdings(portfolio_entries, position_entries)
    return {normalize_ticker(entry.ticker) for entry in merged}


def _followed_and_held(held: set[str]) -> list[str]:
    """Followed names plus all held positions, normalized and de-duplicated."""
    followed = {normalize_ticker(entry.ticker) for entry in parse_portfolio(read_text_or_empty(WATCHLIST_PATH))}
    return sorted(followed | held)


def _trim_tickers(tickers: list[str], max_symbols: int) -> list[str]:
    if max_symbols <= 0 or max_symbols >= len(tickers):
        return tickers  # screen everything
    return tickers[:max_symbols]


def _regime_label(*frames) -> str:
    for df in frames:
        if df is not None and 'Market Context' in df.columns and not df.empty:
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

    held = _held_tickers()
    watchlist = _followed_and_held(held)

    try:
        sp500 = load_sp500_universe(cache)
        companies = dict(sp500.companies)

        # Recommended adds: screen the S&P 500 (plus watchlist) at the tight add
        # gates. Names already held are kept -- a fresh setup on an existing
        # position is still a valid add.
        add_tickers = _trim_tickers(
            list(dict.fromkeys([*sp500.tickers, *watchlist])), max_symbols
        )
        add_universe = UniverseResult(tickers=add_tickers, companies=companies)
        add_config = FilterConfig(
            min_confidence=settings.rec_min_confidence,
            min_reward_risk=settings.rec_min_reward_risk,
            min_avg_volume=settings.min_avg_volume,
            require_regime=settings.require_regime_for_adds,
        )
        recommended = engine.screen(add_universe, config=add_config)

        # Watchlist monitor: ungated analysis of every followed/held name.
        watch_universe = UniverseResult(
            tickers=watchlist, companies={t: companies.get(t, '') for t in watchlist}
        )
        watch_df = engine.analyze(watch_universe, config=FilterConfig.from_settings(settings))

        block = build_snapshot_markdown(
            watch_df,
            recommended,
            settings=settings,
            generated_at=generated_at,
            regime_label=_regime_label(recommended, watch_df),
            watchlist_count=len(watchlist),
            limit=limit,
        )
        print(
            f'Watchlist {len(watchlist)} names; screened {len(add_tickers)} '
            f'-> {len(recommended)} recommended adds.'
        )
    except Exception as exc:  # network / data feed problems must not break the README
        block = build_unavailable_markdown(generated_at=generated_at, reason=type(exc).__name__)
        _LOGGER.exception('Snapshot generation failed: %s', type(exc).__name__)

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
