"""My Positions section: holdings monitor, sleeve panels, allocation, and risk."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import Settings
from src.data.market import earnings_soon as _earnings_soon
from src.data.market import regime_risk_on as _regime_risk_on
from src.data.universe import UniverseResult
from src.data.yahoo_client import YahooFinanceClient
from src.screener.advisor import (
    add_sizing,
    analysis_lookup,
    core_rebalance,
    is_core,
    open_r_multiple,
    pct_to_stop,
    pct_to_target,
    portfolio_open_risk,
    satellite_action,
)
from src.screener.engine import FilterConfig, ScreenerEngine
from src.screener.holdings import (
    SATELLITE,
    PositionEntry,
    account_groups,
    allocation_summary,
    build_monitor,
    concentration_summary,
    count_individual_stocks,
    export_manifest,
    has_accounts,
    merge_holdings,
    parse_account_value,
    parse_portfolio,
    parse_positions,
)
from src.ui.files import (
    PORTFOLIO_FILE,
    POSITIONS_FILE,
    etf_tickers,
    initial_positions_text,
    read_file_text,
    reload_positions_input,
    watchlist_tickers,
)
from src.ui.formatting import apply_formatters, integer, money, percent, score, shares

_MONITOR_FORMATTERS = {
    'Price': money,
    'EMA20': money,
    'SMA50': money,
    'SMA200': money,
    '% vs EMA20': percent,
    '% vs SMA50': percent,
    '% vs SMA200': percent,
    'Entry': money,
    'Unreal P&L %': percent,
    'Shares': shares,
    'Value': money,
    'Weight %': percent,
    'Unreal P&L $': money,
}

_PLAN_FORMATTERS = {
    'Price': money,
    'Entry': money,
    'Stop': money,
    'Target': money,
    'R/R': score,
    'Confidence': integer,
    'Shares': shares,
    'Value': money,
    'Weight %': percent,
    'Unreal P&L %': percent,
    'Add Shares': shares,
    'Add $': money,
    '% to Stop': percent,
    '% to Target': percent,
    'R': score,
}

_CORE_DISPLAY_COLUMNS = (
    'Ticker', 'Account', 'Price', '% vs SMA50', '% vs SMA200', 'Trend',
    'Signal', '50/200 Cross', 'Value', 'Weight %', 'Unreal P&L %', 'Unreal P&L $',
)


def render_positions(
    client: YahooFinanceClient,
    settings: Settings,
    engine: ScreenerEngine,
    config: FilterConfig,
) -> None:
    st.subheader('My Positions')
    st.caption(
        'Your holdings, split into Core (long-term anchors) and Satellite '
        '(tactical names), plus the watchlist you follow. Composition (tickers + '
        'sleeve) lives in portfolio.txt; private sizes live in positions.txt.'
    )

    account_value = _render_inputs()
    if st.button('Analyze Positions', type='primary'):
        _analyze_positions(client, settings, engine, config, account_value)

    monitor = st.session_state.get('monitor_df')
    if monitor is None:
        return
    if 'Sleeve' not in monitor.columns:
        # Stale monitor from an earlier app version (session survives reloads).
        st.info('Your positions view is out of date. Click "Analyze Positions" to refresh.')
        return

    _render_overview(monitor, settings, account_value)


def _render_inputs() -> float:
    """Render the editor + account-value input and return the chosen value."""
    if 'positions_input' not in st.session_state:
        st.session_state['positions_input'] = initial_positions_text()
    with st.expander('Edit private sizes (saved to positions.txt)', expanded=False):
        text = st.text_area(
            'Position sizes',
            key='positions_input',
            height=200,
            help='TICKER, cost_basis, shares per line; [Account] sections and an '
                 '"account_value = N" directive are supported. Kept private (git-ignored).',
        )
        col_save, col_reload = st.columns([1, 1])
        with col_save:
            if st.button(f'Save to {POSITIONS_FILE.name}'):
                try:
                    POSITIONS_FILE.write_text(text, encoding='utf-8')
                except OSError as exc:
                    st.error(f'Could not write {POSITIONS_FILE.name}: {exc}')
                else:
                    st.success(f'Saved your sizes to {POSITIONS_FILE.name}.')
        with col_reload:
            st.button(
                f'Reload from {POSITIONS_FILE.name}',
                on_click=reload_positions_input,
                help='Re-read positions.txt from disk (discards unsaved edits here).',
            )

    text = st.session_state['positions_input']
    directive_value = parse_account_value(text)
    fallback_value = float(st.session_state.get('positions_portfolio_value', 0.0) or 0.0)
    default_value = float(directive_value) if directive_value else fallback_value
    return st.number_input(
        'Account value ($)',
        min_value=0.0,
        value=default_value,
        step=1000.0,
        help='Drives 1%-risk add sizing and allocation. Prefilled from the '
             '"account_value" directive in positions.txt (falls back to your total '
             'position value); override here if needed.',
    )


def _analyze_positions(
    client: YahooFinanceClient,
    settings: Settings,
    engine: ScreenerEngine,
    config: FilterConfig,
    account_value: float,
) -> None:
    """Fetch history, build the monitor, and stash results in session state."""
    text = st.session_state['positions_input']
    portfolio_entries = parse_portfolio(read_file_text(PORTFOLIO_FILE))
    position_entries = parse_positions(text)
    merged = merge_holdings(portfolio_entries, position_entries)
    if not merged:
        st.session_state.pop('monitor_df', None)
        st.warning('No holdings found. Add tickers to portfolio.txt or positions.txt.')
        return

    held = [entry.ticker for entry in merged]
    held_set = set(held)
    watch = [t for t in watchlist_tickers() if t not in held_set]
    all_tickers = held + watch
    with st.spinner(f'Analyzing {len(all_tickers)} symbol(s)...'):
        history = client.fetch_history(all_tickers, period='2y')
        monitor = build_monitor(merged, history, settings)
        watch_entries = [PositionEntry(t, sleeve=SATELLITE) for t in watch]
        watch_monitor = build_monitor(watch_entries, history, settings)
        universe = UniverseResult(tickers=all_tickers, companies={})
        analysis = engine.analyze(universe, config=config)
        funds = etf_tickers(client, all_tickers)

    st.session_state['monitor_df'] = monitor
    st.session_state['watch_monitor'] = watch_monitor
    st.session_state['positions_analysis'] = analysis
    st.session_state['positions_etfs'] = funds
    st.session_state['positions_account_value'] = account_value
    st.session_state['merged_entries'] = merged
    st.session_state['positions_portfolio_value'] = float(monitor['Value'].dropna().sum())
    lookup = analysis_lookup(analysis)
    _, open_risk_pct = portfolio_open_risk(monitor, lookup, account_value)
    st.session_state['positions_open_risk_pct'] = open_risk_pct
    st.session_state['positions_risk_on'] = _regime_risk_on(client, settings)
    st.session_state['positions_earnings'] = _earnings_soon(
        client, held, settings.earnings_blackout_days
    )


def _render_overview(monitor: pd.DataFrame, settings: Settings, account_value: float) -> None:
    analysis = st.session_state.get('positions_analysis', pd.DataFrame())
    watch_monitor = st.session_state.get('watch_monitor', pd.DataFrame())
    etfs = st.session_state.get('positions_etfs', set())
    account_value = st.session_state.get('positions_account_value', account_value)
    merged = st.session_state.get('merged_entries', [])
    lookup = analysis_lookup(analysis)
    open_risk_pct = float(st.session_state.get('positions_open_risk_pct', 0.0))
    risk_on = bool(st.session_state.get('positions_risk_on', True))
    earnings = st.session_state.get('positions_earnings', set())

    if not risk_on:
        st.warning('Risk-off: SPY is below its 200-day — new buys are paused.')
    headroom = max(settings.max_portfolio_risk - open_risk_pct, 0.0)
    held_value = monitor['Value'].dropna()
    if not held_value.empty:
        total = float(held_value.sum())
        cash = max(account_value - total, 0.0)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric('Portfolio value', money(total))
        c2.metric('Unrealized P&L', money(float(monitor['Unreal P&L $'].dropna().sum())))
        c3.metric('Risk headroom', percent(headroom))
        c4.metric('Cash', percent(cash / account_value) if account_value > 0 else '—')

    core_tab, sat_tab, watch_tab = st.tabs(['Core', 'Satellite', 'Watchlist'])
    with core_tab:
        _render_core_panel(monitor)
    with sat_tab:
        _render_satellite_panel(monitor, lookup, account_value, settings, open_risk_pct, earnings)
    with watch_tab:
        _render_watchlist_panel(watch_monitor, lookup, account_value, settings, open_risk_pct)

    _render_allocation_panel(monitor, etfs, settings)
    _render_risk_panel(monitor, lookup, account_value)

    if has_accounts(monitor):
        _render_accounts(monitor)
        _render_concentration(monitor, title='Overall concentration')
    else:
        _render_concentration(monitor)

    _render_publish_button(merged)


def _render_core_panel(monitor: pd.DataFrame) -> None:
    core = monitor[monitor['Sleeve'].map(is_core)]
    st.caption('Long-term anchors (e.g. VTI / VXUS) \u2014 monitored, not traded.')
    if core.empty:
        st.info('No core holdings tagged in portfolio.txt.')
        return
    columns = [c for c in _CORE_DISPLAY_COLUMNS if c in core.columns]
    display = core[columns]
    if not has_accounts(monitor):
        display = display.drop(columns=['Account'], errors='ignore')
    st.dataframe(apply_formatters(display, _MONITOR_FORMATTERS), width='stretch', hide_index=True)


def _render_satellite_panel(
    monitor: pd.DataFrame, lookup: dict, account_value: float, settings: Settings,
    open_risk_pct: float = 0.0, earnings: set[str] | None = None,
) -> None:
    earnings = earnings or set()
    sat = monitor[~monitor['Sleeve'].map(is_core)]
    st.caption(
        'Tactical names with a trade plan and risk-sized add suggestion '
        '(1% account risk, capped by max position weight).'
    )
    if sat.empty:
        st.info('No satellite holdings tagged in portfolio.txt.')
        return
    has_acct = has_accounts(monitor)
    rows = []
    for _, r in sat.iterrows():
        ticker = str(r['Ticker'])
        a = lookup.get(ticker, {})
        current_value = float(r['Value']) if pd.notna(r['Value']) else 0.0
        actionable = bool(a.get('Actionable', False))
        sizing = add_sizing(account_value, settings, a, current_value, open_risk_pct)
        row = {
            'Ticker': ticker,
            'Account': r.get('Account'),
            'Price': r['Price'],
            'Entry': a.get('Entry'),
            'Stop': a.get('Stop'),
            'Target': a.get('Target'),
            'R/R': a.get('R/R'),
            'Shares': r['Shares'],
            'Value': r['Value'],
            'Weight %': r['Weight %'],
            'Unreal P&L %': r['Unreal P&L %'],
            '% to Stop': pct_to_stop(r['Price'], a.get('Stop')),
            '% to Target': pct_to_target(r['Price'], a.get('Target')),
            'R': open_r_multiple(r['Price'], a.get('Entry'), a.get('Stop')),
            'Add Shares': sizing.shares if sizing else None,
            'Add $': sizing.dollars if sizing else None,
            'Earnings': 'soon' if ticker in earnings else '',
            'Action': satellite_action(r, a, sizing, actionable, settings),
        }
        if not has_acct:
            row.pop('Account')
        rows.append(row)
    frame = pd.DataFrame(rows)
    st.dataframe(apply_formatters(frame, _PLAN_FORMATTERS), width='stretch', hide_index=True)


def _render_watchlist_panel(
    watch_monitor: pd.DataFrame, lookup: dict, account_value: float, settings: Settings,
    open_risk_pct: float = 0.0,
) -> None:
    st.caption('Names you follow (no positions). New-entry size assumes a fresh buy.')
    if watch_monitor is None or watch_monitor.empty:
        st.info('Watchlist is empty. Add tickers to watchlist.txt.')
        return
    rows = []
    for _, r in watch_monitor.iterrows():
        ticker = str(r['Ticker'])
        a = lookup.get(ticker, {})
        actionable = bool(a.get('Actionable', False))
        sizing = add_sizing(account_value, settings, a, 0.0, open_risk_pct)
        rows.append({
            'Ticker': ticker,
            'Price': r['Price'],
            'Entry': a.get('Entry'),
            'Stop': a.get('Stop'),
            'Target': a.get('Target'),
            'R/R': a.get('R/R'),
            'Confidence': a.get('Confidence'),
            'Add Shares': sizing.shares if sizing else None,
            'Add $': sizing.dollars if sizing else None,
            'Hint': 'Actionable' if actionable else 'Watch',
        })
    frame = pd.DataFrame(rows)
    st.dataframe(apply_formatters(frame, _PLAN_FORMATTERS), width='stretch', hide_index=True)


def _render_allocation_panel(monitor: pd.DataFrame, etfs: set, settings: Settings) -> None:
    st.markdown('**Allocation vs target**')
    stats = allocation_summary(monitor, settings.core_allocation_min, settings.core_allocation_max)
    if stats is None:
        st.info('Add share counts to your positions to see Core/Satellite allocation.')
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric(
            'Core',
            percent(stats.core_pct),
            help=f'Target {percent(stats.target_min)}\u2013{percent(stats.target_max)}.',
        )
        c2.metric('Satellite', percent(stats.satellite_pct))
        c3.metric('Total value', money(stats.total_value))
        message = (
            f'Core {percent(stats.core_pct)} vs target '
            f'{percent(stats.target_min)}\u2013{percent(stats.target_max)} \u2014 {stats.label}.'
        )
        if stats.within_band:
            st.success(message)
        else:
            st.warning(message)
            _, rebalance_note = core_rebalance(stats)
            if rebalance_note:
                st.caption(rebalance_note)

    count = count_individual_stocks(monitor, etfs)
    cap = settings.max_individual_stocks
    note = f'{count} individual stock(s) (ETFs excluded; cap {cap}).'
    if count > cap:
        st.error(f'{note} Over the diversification cap \u2014 trim or consolidate.')
    elif count >= cap - 2:
        st.warning(f'{note} Approaching the cap.')
    else:
        st.caption(note)


def _render_risk_panel(monitor: pd.DataFrame, lookup: dict, account_value: float) -> None:
    total_risk = 0.0
    for _, r in monitor.iterrows():
        if is_core(r['Sleeve']):
            continue
        shares = r['Shares']
        price = r['Price']
        stop = lookup.get(str(r['Ticker']), {}).get('Stop')
        if (
            shares is not None and not pd.isna(shares)
            and price is not None and not pd.isna(price)
            and stop is not None and not pd.isna(stop)
            and float(price) > float(stop)
        ):
            total_risk += float(shares) * (float(price) - float(stop))

    st.markdown('**Open risk (satellite stops)**')
    c1, c2 = st.columns(2)
    c1.metric('Open risk ($)', money(total_risk))
    if account_value > 0:
        c2.metric('Open risk (% of account)', percent(total_risk / account_value))
    st.caption(
        'Capital lost if every satellite hit its stop today '
        '(\u03a3 shares \u00d7 (price \u2212 stop)). Core holdings are excluded.'
    )


def _render_accounts(monitor: pd.DataFrame) -> None:
    """Per-account value, P&L, and concentration breakdown."""
    st.markdown('**By account**')
    for label, sub in account_groups(monitor):
        held = sub['Value'].dropna()
        with st.expander(f'{label} \u2014 {len(sub)} position(s)', expanded=True):
            if not held.empty:
                c1, c2 = st.columns(2)
                c1.metric('Account value', money(float(held.sum())))
                pnl = sub['Unreal P&L $'].dropna()
                c2.metric('Account P&L', money(float(pnl.sum())) if not pnl.empty else '\u2014')
            _render_concentration(sub)


def _render_concentration(monitor: pd.DataFrame, title: str = 'Concentration') -> None:
    stats = concentration_summary(monitor)
    if stats is None:
        return
    st.markdown(f'**{title}**')
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Positions', stats.positions)
    c2.metric(
        'Largest position',
        percent(stats.largest_weight),
        help=f'{stats.largest_ticker} is your biggest holding.',
    )
    c3.metric(f'Top {min(stats.positions, 5)} weight', percent(stats.top_n_weight))
    c4.metric(
        'Effective holdings',
        f'{stats.effective_positions:.1f}',
        help='Equal-weight-equivalent count (1 / HHI). Far below your actual '
             'position count means a few names dominate.',
    )
    message = (
        f'{stats.label} (HHI {stats.hhi:.2f}). Largest: {stats.largest_ticker} '
        f'at {percent(stats.largest_weight)}; top {min(stats.positions, 5)} '
        f'hold {percent(stats.top_n_weight)} of the book.'
    )
    if stats.label == 'Diversified':
        st.success(message)
    elif stats.label == 'Moderately concentrated':
        st.warning(message)
    else:
        st.error(message)


def _render_publish_button(merged: list) -> None:
    st.markdown('**Publish composition**')
    st.caption(
        'Regenerate the committable portfolio.txt from your current holdings '
        '(tickers + sleeve only \u2014 no sizes).'
    )
    if not merged:
        return
    manifest = export_manifest(merged)
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button(f'Publish to {PORTFOLIO_FILE.name}'):
            try:
                PORTFOLIO_FILE.write_text(manifest, encoding='utf-8')
            except OSError as exc:
                st.error(f'Could not write {PORTFOLIO_FILE.name}: {exc}')
            else:
                st.success(f'Wrote composition to {PORTFOLIO_FILE.name}.')
    with col2:
        st.download_button(
            'Download portfolio.txt',
            data=manifest,
            file_name='portfolio.txt',
            mime='text/plain',
        )
