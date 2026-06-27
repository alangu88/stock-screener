"""Recommended Adds section: screen for fresh setups and log chosen buys."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from src.config import Settings
from src.data.cache import SQLiteCache
from src.data.universe import UniverseResult, load_sp500_universe
from src.data.yahoo_client import YahooFinanceClient
from src.screener.advisor import (
    individual_cap_state,
    recommendation_rows,
    rotation_candidates,
)
from src.screener.engine import FilterConfig, ScreenerEngine
from src.ui.files import (
    append_to_positions,
    etf_tickers,
    held_tickers,
    positions_sections,
    watchlist_tickers,
)
from src.ui.formatting import apply_formatters, integer, money, percent, score, shares

_REC_FORMATTERS = {
    'Confidence': integer,
    'R/R': score,
    'Entry': money,
    'Stop': money,
    'Target': money,
    'Rank Score': score,
    'Add Shares': shares,
    'Add $': money,
}

_ROTATION_FORMATTERS = {
    'Trend': percent,
    'RS': percent,
    'Weight %': percent,
    'Value': money,
    'Unreal P&L %': percent,
}


def render_recommendations(
    cache: SQLiteCache,
    client: YahooFinanceClient,
    settings: Settings,
    engine: ScreenerEngine,
) -> None:
    st.subheader('Recommended Adds')
    st.caption(
        'New high-conviction setups from the S&P 500 plus your watchlist, '
        'excluding names you already hold. Gates are intentionally tight \u2014 '
        'an empty list most days is expected.'
    )
    min_conf, min_rr = _render_gates(settings)
    if st.button('Find recommended adds', type='primary'):
        _find_recommendations(cache, client, settings, engine, min_conf, min_rr)

    recs = st.session_state.get('recommendations')
    if recs is None:
        st.info('Click "Find recommended adds" to scan for fresh setups.')
        return

    st.caption(f'Last run: {st.session_state.get("recommendation_at", "-")}')
    if recs.empty:
        st.success('No high-conviction adds today \u2014 sitting tight.')
        return

    etfs = st.session_state.get('recommendation_etfs', set())
    account_value = float(st.session_state.get('positions_account_value', 0.0) or 0.0)
    table = recommendation_rows(recs, account_value, settings, etfs)

    at_cap, cap_note = _cap_state(settings)
    if at_cap:
        _render_capped(table, cap_note)
    else:
        st.dataframe(apply_formatters(table, _REC_FORMATTERS), width='stretch', hide_index=True)
        if account_value <= 0:
            st.caption('Set your account value under My Positions to see risk-based add sizes.')

    _render_add_to_positions(table)


def _render_gates(settings: Settings) -> tuple[float, float]:
    c1, c2 = st.columns(2)
    min_conf = c1.number_input(
        'Min confidence',
        min_value=0.0,
        max_value=100.0,
        value=float(settings.rec_min_confidence),
        step=5.0,
        help='Only surface setups scoring at least this confidence (0\u2013100).',
    )
    min_rr = c2.number_input(
        'Min reward/risk',
        min_value=0.0,
        value=float(settings.rec_min_reward_risk),
        step=0.5,
        help='Require at least this reward-to-risk multiple on the trade plan.',
    )
    return float(min_conf), float(min_rr)


def _find_recommendations(
    cache: SQLiteCache,
    client: YahooFinanceClient,
    settings: Settings,
    engine: ScreenerEngine,
    min_conf: float,
    min_rr: float,
) -> None:
    with st.spinner('Screening S&P 500 + watchlist for high-conviction setups...'):
        universe = load_sp500_universe(cache)
        watch = watchlist_tickers()
        tickers = list(dict.fromkeys([*universe.tickers, *watch]))
        rec_universe = UniverseResult(tickers=tickers, companies=dict(universe.companies))
        rec_config = FilterConfig(
            min_confidence=min_conf,
            min_reward_risk=min_rr,
            min_avg_volume=settings.min_avg_volume,
        )
        recs = engine.screen(rec_universe, config=rec_config)
        held = held_tickers()
        if not recs.empty and held:
            recs = recs[~recs['Ticker'].isin(held)]
        recs = recs.sort_values('Rank Score', ascending=False).reset_index(drop=True)
        funds = etf_tickers(client, list(recs['Ticker'])) if not recs.empty else set()
    st.session_state['recommendations'] = recs
    st.session_state['recommendation_etfs'] = funds
    st.session_state['recommendation_at'] = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')


def _cap_state(settings: Settings) -> tuple[bool, str]:
    """Session-aware wrapper over ``advisor.individual_cap_state``."""
    monitor = st.session_state.get('monitor_df')
    etfs = st.session_state.get('positions_etfs', set())
    return individual_cap_state(monitor, etfs, settings)


def _render_capped(table: pd.DataFrame, cap_note: str) -> None:
    """At the individual-stock cap: show funds, flag stocks, suggest rotations."""
    st.warning(cap_note)
    etf_picks = table[table['Type'] == 'ETF']
    stock_picks = table[table['Type'] == 'Stock']
    if not etf_picks.empty:
        st.markdown('**Fund picks (allowed)**')
        st.dataframe(
            apply_formatters(etf_picks, _REC_FORMATTERS), width='stretch', hide_index=True
        )
    if not stock_picks.empty:
        st.markdown('**Single-stock picks (rotate, don\u2019t add)**')
        st.dataframe(
            apply_formatters(stock_picks, _REC_FORMATTERS), width='stretch', hide_index=True
        )
    monitor = st.session_state.get('monitor_df')
    analysis = st.session_state.get('positions_analysis', pd.DataFrame())
    held_etfs = st.session_state.get('positions_etfs', set())
    rotation = rotation_candidates(monitor, analysis, held_etfs)
    if not rotation.empty:
        st.markdown('**Rotation candidates (weakest holdings to trim)**')
        st.caption(
            'Held single-stock names ranked weakest-first (furthest below the '
            '200-day trend, then weakest relative strength, then smallest position). '
            'Free up a slot here before adding a new name.'
        )
        st.dataframe(
            apply_formatters(rotation, _ROTATION_FORMATTERS),
            width='stretch',
            hide_index=True,
        )


def _render_add_to_positions(table: pd.DataFrame) -> None:
    """Append a chosen recommendation to positions.txt (closes the research loop)."""
    if table is None or table.empty or 'Ticker' not in table.columns:
        return
    with st.expander('Add a pick to positions.txt', expanded=False):
        st.caption(
            'Record a planned or filled buy. Writes a "TICKER, cost_basis, shares" '
            'line to positions.txt (git-ignored). Reload positions afterwards to see it.'
        )
        tickers = [str(t) for t in table['Ticker'].tolist()]
        picked = st.selectbox('Recommendation', tickers, key='add_pos_ticker')
        row = table[table['Ticker'].astype(str) == picked].iloc[0].to_dict()

        sections = positions_sections()
        section_options = [*sections, '(no section)']
        section_choice = st.selectbox('Account section', section_options, key='add_pos_section')

        default_shares = float(row['Add Shares']) if pd.notna(row.get('Add Shares')) else 0.0
        default_entry = float(row['Entry']) if pd.notna(row.get('Entry')) else 0.0
        c1, c2 = st.columns(2)
        qty = c1.number_input('Shares', min_value=0.0, value=default_shares, step=0.001, format='%.3f')
        cost_basis = c2.number_input('Cost basis ($)', min_value=0.0, value=default_entry, step=1.0)

        if st.button(f'Append {picked} to positions.txt'):
            if qty <= 0:
                st.warning('Enter a share count greater than zero.')
            else:
                section = None if section_choice == '(no section)' else section_choice
                try:
                    append_to_positions(section, picked, cost_basis or None, qty)
                except OSError as exc:
                    st.error(f'Could not write positions.txt: {exc}')
                else:
                    where = f'[{section}]' if section else 'positions.txt'
                    st.success(
                        f'Added {picked} ({qty:g} sh) to {where}. '
                        'Reload positions and re-run Analyze to include it.'
                    )
