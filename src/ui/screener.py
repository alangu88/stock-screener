"""Screener view: run the screen over the S&P 500 + watchlist and rank results."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from src.config import Settings
from src.data.cache import SQLiteCache
from src.data.universe import UniverseResult, load_sp500_universe
from src.data.yahoo_client import YahooFinanceClient
from src.screener.engine import FilterConfig, ScreenerEngine
from src.ui.files import watchlist_tickers
from src.ui.formatting import apply_formatters, dollars, integer, money, percent, score

# Columns shown in the screener table, in display order.
_DISPLAY_COLUMNS = (
    'Ticker',
    'Company Name',
    'Setup',
    'Confidence',
    'Rank Score',
    'Entry',
    'Stop',
    'Target',
    'R/R',
    'Reward %',
    'Risk %',
    'Trend Score',
    'Rel Volume',
    'Beta',
    'Return 3M',
    'ATR %',
    'Dist 200D %',
    'Dollar ADV',
    'Div Yield',
    'Sector',
    'Market Cap',
    'Market Context',
)

_FORMATTERS = {
    'Confidence': integer,
    'Rank Score': score,
    'R/R': score,
    'Entry': money,
    'Stop': money,
    'Target': money,
    'Reward %': percent,
    'Risk %': percent,
    'Trend Score': score,
    'Rel Volume': score,
    'Beta': score,
    'Return 3M': percent,
    'ATR %': percent,
    'Dist 200D %': percent,
    'Div Yield': percent,
    'Dollar ADV': dollars,
    'Market Cap': money,
}


def render_screener(
    cache: SQLiteCache,
    client: YahooFinanceClient,
    settings: Settings,
    engine: ScreenerEngine,
    config: FilterConfig,
) -> None:
    st.subheader('Screener')
    st.caption(
        'Ranked high-conviction technical setups from the S&P 500 plus your '
        'watchlist. Entry / Stop / Target are structural, data-derived levels. '
        'Gates are intentionally tight, so a short list is expected.'
    )
    if st.button('Run screen', type='primary'):
        _run_screen(cache, client, engine, config)

    results = st.session_state.get('screen_results')
    if results is None:
        st.info('Click "Run screen" to scan the S&P 500 + watchlist for fresh setups.')
        return

    st.caption(f'Last run: {st.session_state.get("screen_at", "-")}')
    if results.empty:
        st.success('No candidates cleared the gates \u2014 nothing actionable right now.')
        return

    display = results.reindex(columns=[c for c in _DISPLAY_COLUMNS if c in results.columns])
    st.dataframe(apply_formatters(display, _FORMATTERS), width='stretch', hide_index=True)
    st.caption(f'{len(results)} candidate(s), ranked by market-context-adjusted score.')


def _run_screen(
    cache: SQLiteCache,
    client: YahooFinanceClient,
    engine: ScreenerEngine,
    config: FilterConfig,
) -> None:
    universe = load_sp500_universe(cache)
    tickers = list(dict.fromkeys([*universe.tickers, *watchlist_tickers()]))
    full = UniverseResult(tickers=tickers, companies=dict(universe.companies))
    with st.spinner(f'Screening {len(tickers)} names\u2026'):
        results = engine.screen(full, config=config)
    if not results.empty:
        results = results.sort_values('Rank Score', ascending=False).reset_index(drop=True)
    st.session_state['screen_results'] = results
    st.session_state['screen_at'] = datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')
