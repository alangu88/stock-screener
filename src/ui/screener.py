"""Screener view: run the screen over the S&P 500 + watchlist and rank results."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from src.config import Settings
from src.core.scoring import EntryQualityScorer
from src.data.cache import SQLiteCache
from src.data.universe import UniverseResult, load_sp500_universe
from src.data.yahoo_client import YahooFinanceClient
from src.screener.engine import FilterConfig, ScreenerEngine
from src.ui.files import watchlist_tickers
from src.ui.formatting import apply_formatters, dollars, integer, money, percent, score

_SESSION_FALLBACK: dict[str, object] = {}
_SESSION_LOCK = threading.Lock()


def _attach_script_context(thread: threading.Thread) -> None:
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import (
            add_script_run_ctx,
            get_script_run_ctx,
        )

        ctx = get_script_run_ctx()
        if ctx is not None:
            add_script_run_ctx(ctx, thread)
    except Exception:
        pass


def _can_write_session_state() -> bool:
    if threading.current_thread() is not threading.main_thread():
        return False
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import (
            get_script_run_ctx,
        )

        return get_script_run_ctx() is not None
    except Exception:
        return False


def _state_get(key: str, default=None):
    with _SESSION_LOCK:
        if key in _SESSION_FALLBACK:
            return _SESSION_FALLBACK[key]
    if threading.current_thread() is not threading.main_thread():
        return default
    try:
        return st.session_state.get(key, default)
    except Exception:
        return default


def _state_set(key: str, value) -> None:
    with _SESSION_LOCK:
        _SESSION_FALLBACK[key] = value
    if not _can_write_session_state():
        return
    try:
        st.session_state.__setitem__(key, value)
    except Exception:
        try:
            st.session_state[key] = value
        except Exception:
            pass


def _state_pop(key: str, default=None):
    with _SESSION_LOCK:
        fallback_value = _SESSION_FALLBACK.pop(key, default)
    if threading.current_thread() is not threading.main_thread():
        return fallback_value
    try:
        return st.session_state.pop(key, default)
    except Exception:
        return fallback_value


def _sector_summary(results: pd.DataFrame) -> pd.DataFrame:
    if results is None or results.empty or 'Sector' not in results.columns:
        return pd.DataFrame(
            columns=['Sector', 'Candidates', 'Avg Confidence', 'Avg Rank Score', 'Avg Sector Trend']
        )
    grouped = (
        results.groupby('Sector', dropna=False)
        .agg(
            Candidates=('Ticker', 'count'),
            Avg_Confidence=('Confidence', 'mean'),
            Avg_Rank=('Rank Score', 'mean'),
            Avg_Sector_Trend=('Sector Trend', 'mean'),
        )
        .reset_index()
    )
    grouped = grouped.sort_values(['Avg_Rank', 'Avg_Confidence'], ascending=False)
    grouped.columns = [
        'Sector',
        'Candidates',
        'Avg Confidence',
        'Avg Rank Score',
        'Avg Sector Trend',
    ]
    return grouped


def _screen_quality_summary(results: pd.DataFrame) -> pd.DataFrame:
    """Summarize broad tape health, sector leadership, and setup quality."""
    if results is None or results.empty:
        return pd.DataFrame(columns=['Metric', 'Value', 'Detail'])

    avg_confidence = float(results['Confidence'].mean()) if 'Confidence' in results.columns else 0.0
    avg_rank = float(results['Rank Score'].mean()) if 'Rank Score' in results.columns else 0.0
    avg_sector_trend = (
        float(results['Sector Trend'].mean()) if 'Sector Trend' in results.columns else 0.0
    )
    avg_rr = float(results['R/R'].mean()) if 'R/R' in results.columns else 0.0

    breadth = (
        'Strong' if avg_sector_trend > 0.02 else 'Moderate' if avg_sector_trend >= -0.01 else 'Weak'
    )
    sector_lead = 'Strong' if avg_rank >= 75 else 'Moderate' if avg_rank >= 60 else 'Weak'
    quality = (
        'Strong'
        if avg_confidence >= 75 and avg_rr >= 2.0
        else 'Moderate'
        if avg_confidence >= 60
        else 'Weak'
    )

    return pd.DataFrame(
        [
            {
                'Metric': 'Market Breadth',
                'Value': breadth,
                'Detail': f'Avg sector trend: {avg_sector_trend:.2%}',
            },
            {
                'Metric': 'Sector Leadership',
                'Value': sector_lead,
                'Detail': f'Avg rank score: {avg_rank:.1f}',
            },
            {
                'Metric': 'Setup Quality',
                'Value': quality,
                'Detail': f'Avg confidence: {avg_confidence:.1f} | avg R/R: {avg_rr:.2f}',
            },
        ]
    )


def _filter_results_by_sector(
    results: pd.DataFrame, sectors: tuple[str, ...] | list[str] | None
) -> pd.DataFrame:
    if results is None or results.empty or 'Sector' not in results.columns:
        return results.copy() if isinstance(results, pd.DataFrame) else pd.DataFrame()
    selected = tuple(str(item).strip() for item in (sectors or ()) if str(item).strip())
    if not selected:
        return results.copy()
    return results[results['Sector'].astype(str).isin(selected)].copy()


def _entry_quality_summary(results: pd.DataFrame) -> pd.DataFrame:
    """Add a clear 'quality dip vs distribution trap' readout to the UI."""
    if results is None or results.empty:
        return pd.DataFrame(columns=['Ticker', 'Entry Quality', 'Verdict'])

    scorer = EntryQualityScorer()
    rows = []
    for row in results.to_dict(orient='records'):
        trend = float(row.get('Trend Score', 0.0) or 0.0)
        support = max(0.0, min(1.0, float((row.get('Dist 200D %', 0.0) or 0.0) * 0.1 + 0.5)))
        volume = max(0.0, min(1.0, float((row.get('Rel Volume', 0.0) or 0.0) / 2.0)))
        rs = max(0.0, min(1.0, float((row.get('RS Outperformance', 0.0) or 0.0) * 1.25 + 0.5)))
        risk = max(0.0, min(1.0, float((row.get('R/R', 0.0) or 0.0) / 5.0)))

        accumulation_distribution = max(
            0.0,
            min(1.0, float((row.get('Rel Volume', 0.0) or 0.0) * 0.6 + (trend * 0.4))),
        )
        score = scorer.score(
            trend_integrity=trend,
            support_quality=support,
            volume_absorption=volume,
            accumulation_distribution=accumulation_distribution,
            relative_strength=rs,
            risk_quality=risk,
        )
        rows.append(
            {
                'Ticker': row.get('Ticker', ''),
                'Entry Quality': score.total,
                'Verdict': score.verdict,
            }
        )

    return pd.DataFrame(rows).sort_values(['Entry Quality', 'Ticker'], ascending=[False, True])


def _setup_reason_summary(results: pd.DataFrame) -> pd.DataFrame:
    """Summarize the main technical reasons a candidate is attractive."""
    if results is None or results.empty:
        return pd.DataFrame(
            columns=[
                'Ticker',
                'Trend Score',
                'RS Outperformance',
                'Rel Volume',
                'R/R',
                'Key Driver',
                'Entry Quality',
            ]
        )

    rows = []
    for row in results.to_dict(orient='records'):
        trend = float(row.get('Trend Score', 0.0) or 0.0)
        rs = float(row.get('RS Outperformance', 0.0) or 0.0)
        rel_volume = float(row.get('Rel Volume', 0.0) or 0.0)
        rr = float(row.get('R/R', 0.0) or 0.0)
        if trend >= 0.7 and rs >= 0.10 and rel_volume >= 1.2:
            key_driver = 'Trend leadership'
        elif trend >= 0.6:
            key_driver = 'Strong trend quality'
        elif rs >= 0.10:
            key_driver = 'Relative strength'
        elif rel_volume >= 1.2:
            key_driver = 'Volume confirmation'
        elif rr >= 2.0:
            key_driver = 'Reward quality'
        else:
            key_driver = 'Balanced setup'
        rows.append(
            {
                'Ticker': row.get('Ticker', ''),
                'Trend Score': trend,
                'RS Outperformance': rs,
                'Rel Volume': rel_volume,
                'R/R': rr,
                'Key Driver': key_driver,
                'Entry Quality': row.get('Entry Quality', row.get('Verdict', '')),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ['Trend Score', 'R/R', 'Ticker'], ascending=[False, False, True]
    )


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
    'Sector Trend',
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
    'Sector Trend': percent,
    'Market Cap': money,
}


def _risk_plan_for_results(
    results: pd.DataFrame,
    account_size: float,
    risk_pct: float,
) -> pd.DataFrame:
    """Return a compact risk-sizing table for each candidate setup."""
    if results is None or results.empty:
        return pd.DataFrame(
            columns=[
                'Ticker',
                'Entry',
                'Stop',
                'Risk Dollars',
                'Risk Per Share',
                'Shares',
                'Position Value',
            ]
        )

    rows = []
    for row in results.to_dict(orient='records'):
        entry = row.get('Entry')
        stop = row.get('Stop')
        if entry is None or stop is None or pd.isna(entry) or pd.isna(stop):
            continue
        entry_value = float(entry)
        stop_value = float(stop)
        risk_per_share = abs(entry_value - stop_value)
        if risk_per_share <= 0:
            continue
        risk_dollars = float(account_size) * (float(risk_pct) / 100.0)
        shares = risk_dollars / risk_per_share
        position_value = shares * entry_value
        rows.append(
            {
                'Ticker': row.get('Ticker', ''),
                'Entry': entry_value,
                'Stop': stop_value,
                'Risk Dollars': risk_dollars,
                'Risk Per Share': risk_per_share,
                'Shares': shares,
                'Position Value': position_value,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(
            columns=[
                'Ticker',
                'Entry',
                'Stop',
                'Risk Dollars',
                'Risk Per Share',
                'Shares',
                'Position Value',
            ]
        )
    return out.sort_values(['Risk Dollars', 'Ticker'], ascending=[False, True]).reset_index(
        drop=True
    )


def _rejected_names_panel(cache: SQLiteCache, engine: ScreenerEngine, config: FilterConfig) -> None:
    """Display names that cleared analysis but failed the actionability gates."""
    universe = load_sp500_universe(cache)
    tickers = list(dict.fromkeys([*universe.tickers, *watchlist_tickers()]))
    full = UniverseResult(tickers=tickers, companies=dict(universe.companies))
    analysis = engine.analyze(full, config=config)
    if analysis is None or analysis.empty:
        return
    rejected = analysis[~analysis['Actionable']].copy()
    if rejected.empty:
        return
    rejected = rejected.sort_values(['Confidence', 'R/R'], ascending=[False, False]).head(20)
    display = rejected.reindex(
        columns=['Ticker', 'Company Name', 'Setup', 'Confidence', 'R/R', 'Filter Reasons']
    )
    st.subheader('Why filtered out')
    st.caption('High-quality chart setups that were screened out by the recommendation gates.')
    st.dataframe(
        apply_formatters(
            display,
            {
                'Confidence': integer,
                'R/R': score,
            },
        ),
        hide_index=True,
        width='stretch',
    )


def _screen_worker(
    cache: SQLiteCache,
    engine: ScreenerEngine,
    config: FilterConfig,
    cancel_event: threading.Event,
) -> None:
    """Run the full screen in a worker thread so the UI remains responsive.

    The heavy screening work is not interruptible from inside a single
    Streamlit callback; by moving it to a background thread and checking the
    cancellation flag before and between expensive steps, the user can stop the
    run without the app appearing to hang on a stale or already-cancelled run.
    """
    try:
        if cancel_event is not None and cancel_event.is_set():
            _state_set('screen_results', _empty_screen_frame())
            _state_set('screen_cancelled', True)
            _state_set('screen_running', False)
            return

        universe = None
        if cache is not None:
            try:
                universe = load_sp500_universe(cache)
            except Exception:
                universe = None
        if universe is None:
            universe = UniverseResult(tickers=[], companies={})

        tickers = list(dict.fromkeys([*universe.tickers, *watchlist_tickers()]))
        full = UniverseResult(tickers=tickers, companies=dict(universe.companies))
        if cancel_event is not None and cancel_event.is_set():
            _state_set('screen_results', _empty_screen_frame())
            _state_set('screen_cancelled', True)
            _state_set('screen_running', False)
            return

        inputs = engine._fetch_inputs(full, force_refresh=False)
        if cancel_event is not None and cancel_event.is_set():
            _state_set('screen_results', _empty_screen_frame())
            _state_set('screen_cancelled', True)
            _state_set('screen_running', False)
            return
        if inputs is None:
            _state_set('screen_results', _empty_screen_frame())
            _state_set('screen_running', False)
            return

        rows = []
        total = len(inputs.tickers)
        for idx, ticker in enumerate(inputs.tickers, start=1):
            if cancel_event is not None and cancel_event.is_set():
                _state_set('screen_results', _empty_screen_frame())
                _state_set('screen_cancelled', True)
                _state_set('screen_running', False)
                return
            row = engine._evaluate_ticker(ticker, inputs, full, config)
            if cancel_event is not None and cancel_event.is_set():
                _state_set('screen_results', _empty_screen_frame())
                _state_set('screen_cancelled', True)
                _state_set('screen_running', False)
                return
            if row is not None:
                rows.append(row)
            if idx % 25 == 0 or idx == total:
                _state_set('screen_progress', min(idx / total, 1.0))

        results = pd.DataFrame(rows)
        if not results.empty:
            results = results.sort_values('Rank Score', ascending=False).reset_index(drop=True)
        _state_set('screen_results', results if not results.empty else _empty_screen_frame())
        _state_set('screen_at', datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC'))
        _state_set('screen_cancelled', False)
    except Exception as err:  # pragma: no cover - UI surface only.
        _state_set('screen_results', _empty_screen_frame())
        _state_set('screen_error', str(err))
        _state_set('screen_cancelled', False)
    finally:
        _state_set('screen_running', False)
        _state_pop('screen_progress', None)
        _state_pop('screen_worker', None)
        try:
            st.rerun()
        except Exception:
            pass


def _empty_screen_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=['Ticker', 'Company Name', 'Setup', 'Confidence', 'Rank Score'])


def _sync_screen_worker_state() -> None:
    worker = _state_get('screen_worker')
    if worker is None or not isinstance(worker, threading.Thread):
        return
    if worker.is_alive():
        return
    _state_set('screen_running', False)
    _state_set('screen_cancelled', False)
    _state_pop('screen_worker', None)
    try:
        st.rerun()
    except Exception:
        pass


def render_screener(
    cache: SQLiteCache,
    client: YahooFinanceClient,
    settings: Settings,
    engine: ScreenerEngine,
    config: FilterConfig,
    view=None,
) -> None:
    st.subheader('Screener')
    st.caption(
        'Ranked high-conviction technical setups from the S&P 500 plus your '
        'watchlist. Entry / Stop / Target are structural, data-derived levels. '
        'Gates are intentionally tight, so a short list is expected.'
    )

    if st.button('Run screen', type='primary', key='run_screen_button'):
        _state_set('screen_running', True)
        _state_set('screen_cancelled', False)
        _state_pop('screen_error', None)
        cancel_event = threading.Event()
        _state_set('screen_cancel_event', cancel_event)
        worker = threading.Thread(
            target=_screen_worker,
            args=(cache, engine, config, cancel_event),
            daemon=True,
        )
        _attach_script_context(worker)
        _state_set('screen_worker', worker)
        worker.start()

    _sync_screen_worker_state()

    if _state_get('screen_running'):
        worker = _state_get('screen_worker')
        if isinstance(worker, threading.Thread) and worker.is_alive():
            time.sleep(0.2)
            st.rerun()

        progress = _state_get('screen_progress', 0.0)
        st.markdown(
            """
            <div class="screen-status-panel">
                <span class="screen-status-pill">LIVE</span>
                <span class="screen-status-text">Screening universe — stop anytime</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if progress:
            st.progress(float(progress), text='Scanning names...')
        stop_col, _ = st.columns([1, 2])
        with stop_col:
            if st.button('Stop screening', key='stop_screen_button', type='secondary'):
                event = _state_get('screen_cancel_event')
                if event is not None:
                    event.set()
                _state_set('screen_running', False)
                _state_set('screen_cancelled', True)
                st.warning('Screening cancelled.')
        return

    results = _state_get('screen_results')
    if results is None:
        st.info('Click "Run screen" to scan the S&P 500 + watchlist for fresh setups.')
        return

    st.caption(f'Last run: {_state_get("screen_at", "-")}')
    if results.empty:
        st.success('No candidates cleared the gates \u2014 nothing actionable right now.')
        _rejected_names_panel(cache, engine, config)
        return

    quality = _screen_quality_summary(results)
    if not quality.empty:
        st.subheader('Screen quality summary')
        metric_cols = st.columns(len(quality))
        for idx, row in enumerate(quality.itertuples(index=False)):
            with metric_cols[idx]:
                st.metric(row.Metric, row.Value, row.Detail)

    summary = st.columns(3)
    with summary[0]:
        st.metric('Candidates', len(results))
    with summary[1]:
        best_conf = float(results['Confidence'].max()) if 'Confidence' in results.columns else 0.0
        st.metric('Best Confidence', f'{best_conf:.0f}')
    with summary[2]:
        market_context = (
            results['Market Context'].mode().iloc[0]
            if 'Market Context' in results.columns
            else 'Neutral'
        )
        st.metric('Tape', str(market_context))

    entry_quality = _entry_quality_summary(results)
    if not entry_quality.empty:
        st.subheader('Entry quality')
        st.caption(
            'Strong dip = better buyable pullback; distribution trap = lower probability entry.'
        )
        st.dataframe(
            apply_formatters(
                entry_quality.head(5),
                {'Entry Quality': score},
            ),
            hide_index=True,
            width='stretch',
        )

    setup_summary = _setup_reason_summary(results)
    if not setup_summary.empty:
        st.subheader('What is driving this setup')
        st.caption('The main technical reasons the current candidates are scoring well.')
        st.dataframe(
            apply_formatters(
                setup_summary.head(5),
                {
                    'Trend Score': score,
                    'RS Outperformance': score,
                    'Rel Volume': score,
                    'R/R': score,
                },
            ),
            hide_index=True,
            width='stretch',
        )

    sector_options = []
    if 'Sector' in results.columns:
        sector_options = sorted({str(value) for value in results['Sector'].dropna().unique()})

    filtered_results = results
    if sector_options:
        selected_sectors = st.multiselect(
            'Filter by sector',
            options=sector_options,
            default=sector_options,
            key='sector_filter',
            help='Focus the leaderboard and table on the sectors currently showing the strongest leadership.',
        )
        filtered_results = _filter_results_by_sector(results, selected_sectors)

    summary = _sector_summary(filtered_results)
    if not summary.empty:
        st.subheader('Sector leadership')
        st.dataframe(
            apply_formatters(
                summary.head(5),
                {'Avg Confidence': score, 'Avg Rank Score': score, 'Avg Sector Trend': percent},
            ),
            hide_index=True,
            width='stretch',
        )

    display = filtered_results.reindex(
        columns=[c for c in _DISPLAY_COLUMNS if c in filtered_results.columns]
    )
    st.dataframe(apply_formatters(display, _FORMATTERS), width='stretch', hide_index=True)

    if view is not None:
        risk_plan = _risk_plan_for_results(
            display,
            account_size=getattr(view, 'account_size', 10_000.0),
            risk_pct=getattr(view, 'risk_pct', 1.0),
        )
        if not risk_plan.empty:
            st.subheader('Risk plan')
            st.caption('Trade sizing based on your account size and risk-per-trade setting.')
            st.dataframe(
                apply_formatters(
                    risk_plan,
                    {
                        'Entry': money,
                        'Stop': money,
                        'Risk Dollars': dollars,
                        'Risk Per Share': money,
                        'Shares': integer,
                        'Position Value': dollars,
                    },
                ),
                hide_index=True,
                width='stretch',
            )

    st.caption(
        f'{len(filtered_results)} candidate(s) shown after sector filtering ({len(results)} total).'
    )
    _rejected_names_panel(cache, engine, config)


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
