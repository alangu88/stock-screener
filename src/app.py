from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.analysis.indicators import atr, compute_indicators
from src.config import Settings, load_settings
from src.data.cache import SQLiteCache
from src.data.universe import UniverseResult, load_sp500_universe
from src.data.yahoo_client import YahooFinanceClient
from src.export.csv_export import to_csv_bytes
from src.screener.backtest import (
    BacktestParams,
    stats_to_frame,
    summarize,
    summarize_by_confidence,
    summarize_by_setup,
    trades_to_frame,
)
from src.screener.engine import FilterConfig, ScreenerEngine
from src.screener.holdings import (
    CORE,
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
from src.screener.portfolio import PortfolioConfig, sleeve_summary
from src.screener.result import SORTABLE_COLUMNS
from src.screener.setups import BREAKOUT, CONTRACTION, PULLBACK
from src.screener.sizing import suggest_add_size
from src.screener.strategy import StrategyConfig

st.set_page_config(page_title='S&P 500 Stock Screener', layout='wide')

PAGE_SIZE_OPTIONS = [10, 25, 50, 100]
CHART_PERIODS = ['1mo', '3mo', '6mo', '1y', '2y', '5y']
SETUP_OPTIONS = (BREAKOUT, CONTRACTION, PULLBACK)


@dataclass
class ViewOptions:
    sort_column: str
    sort_desc: bool
    page_size: int
    rsi_period: int
    run_scan: bool


@st.cache_resource
def get_services() -> tuple[Settings, SQLiteCache, YahooFinanceClient, ScreenerEngine]:
    settings = load_settings()
    cache = SQLiteCache(settings.cache_dir)
    client = YahooFinanceClient(settings=settings, cache=cache)
    engine = ScreenerEngine(
        client=client,
        strategy=StrategyConfig.from_settings(settings),
        portfolio=PortfolioConfig.from_settings(settings),
    )
    return settings, cache, client, engine


def _fmt(value, spec: str = '.2f', scale: float = 1.0, suffix: str = '') -> str:
    if pd.isna(value) or not math.isfinite(float(value)):
        return ''
    return f'{float(value) * scale:{spec}}{suffix}'


def _human_number(value) -> str:
    if pd.isna(value):
        return ''
    abs_v = abs(value)
    if abs_v >= 1e12:
        return f'{value / 1e12:.2f}T'
    if abs_v >= 1e9:
        return f'{value / 1e9:.2f}B'
    if abs_v >= 1e6:
        return f'{value / 1e6:.2f}M'
    return f'{value:,.2f}'


def _money(value) -> str:
    return _fmt(value, '.2f')


def _percent(value) -> str:
    return _fmt(value, '.2f', 100, '%')


def _percent_int(value) -> str:
    return _fmt(value, '.0f', 100, '%')


def _score(value) -> str:
    return _fmt(value, '.2f')


def _integer(value) -> str:
    return _fmt(value, '.0f')


def _multiple(value) -> str:
    return _fmt(value, '.2f', 1.0, 'x')


def _r_multiple(value) -> str:
    return _fmt(value, '+.2f', 1.0, 'R')


def _apply_formatters(df: pd.DataFrame, formatters: dict) -> pd.DataFrame:
    """Format the columns named in ``formatters``; leave the rest untouched."""
    out = df.copy()
    for column, formatter in formatters.items():
        if column in out.columns:
            out[column] = out[column].map(formatter)
    return out


# Column -> formatter. Anything absent is left untouched (e.g. text columns).
_DISPLAY_FORMATTERS = {
    'Market Cap': _human_number,
    'PE Ratio': _money,
    'Revenue Growth': _percent,
    'Price': _money,
    'Entry': _money,
    'Stop': _money,
    'Target': _money,
    'Risk %': _percent,
    'Reward %': _percent,
    'R/R': _score,
    'Confidence': _integer,
    'Rank Score': _score,
    'Trend Score': _score,
    'RS Outperformance': _percent,
    'Rel Volume': _multiple,
    'Core Score': _score,
    'Position Size %': _percent,
    'Risk Contribution %': _percent,
}


def _prepare_display_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    return _apply_formatters(df, _DISPLAY_FORMATTERS)



def _build_chart(
    client: YahooFinanceClient,
    settings: Settings,
    ticker: str,
    period: str,
    rsi_period: int,
    plan: dict | None = None,
) -> tuple[go.Figure | None, float | None]:
    history_map = client.fetch_history([ticker], period=period, interval='1d')
    df = history_map.get(ticker, pd.DataFrame()).copy()
    if df.empty:
        return None, None

    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    if any(col not in df.columns for col in required_cols):
        return None, None

    chart_df = df[required_cols].dropna(subset=['Open', 'High', 'Low', 'Close']).copy()
    if chart_df.empty:
        return None, None

    short_w = settings.sma_short_window
    long_w = settings.sma_long_window
    ema_w = settings.ema_window
    indicators = compute_indicators(
        df,
        rsi_period=rsi_period,
        volume_window=20,
        sma_windows=(short_w, long_w),
        ema_windows=(ema_w,),
    )
    chart_df['EMA'] = indicators[f'EMA{ema_w}']
    chart_df['SMA_SHORT'] = indicators[f'SMA{short_w}']
    chart_df['SMA_LONG'] = indicators[f'SMA{long_w}']
    chart_df['RSI'] = indicators['RSI']
    chart_df['VOL_AVG'] = indicators['VOL_AVG']

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.58, 0.22, 0.20],
        subplot_titles=(f'{ticker} Price', 'RSI', 'Volume'),
    )

    fig.add_trace(
        go.Candlestick(
            x=chart_df.index,
            open=chart_df['Open'],
            high=chart_df['High'],
            low=chart_df['Low'],
            close=chart_df['Close'],
            name='Price',
            increasing_line_color='#16A34A',
            decreasing_line_color='#DC2626',
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=chart_df.index, y=chart_df['EMA'], mode='lines', name=f'EMA {ema_w}', line=dict(color='#0284C7', width=1.5)),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=chart_df.index, y=chart_df['SMA_SHORT'], mode='lines', name=f'SMA {short_w}', line=dict(color='#16A34A', width=1.5)),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=chart_df.index, y=chart_df['SMA_LONG'], mode='lines', name=f'SMA {long_w}', line=dict(color='#B45309', width=1.5)),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(x=chart_df.index, y=chart_df['RSI'], mode='lines', name='RSI', line=dict(color='#7C2D12', width=1.5)),
        row=2,
        col=1,
    )
    fig.add_hline(y=70, line_dash='dash', line_color='#DC2626', row=2, col=1)
    fig.add_hline(y=30, line_dash='dash', line_color='#059669', row=2, col=1)

    fig.add_trace(
        go.Bar(x=chart_df.index, y=chart_df['Volume'], name='Volume', marker_color='#64748B', opacity=0.55),
        row=3,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=chart_df.index, y=chart_df['VOL_AVG'], mode='lines', name='Vol Avg 20', line=dict(color='#334155', width=1.5)),
        row=3,
        col=1,
    )

    fig.update_layout(
        height=820,
        showlegend=True,
        template='plotly_white',
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis_rangeslider_visible=False,
    )
    _overlay_plan(fig, plan)

    fig.update_yaxes(title_text='Price', row=1, col=1)
    fig.update_yaxes(title_text='RSI', row=2, col=1, range=[0, 100])
    fig.update_yaxes(title_text='Volume', row=3, col=1)

    atr_series = atr(chart_df['High'], chart_df['Low'], chart_df['Close'])
    last_close = float(chart_df['Close'].iloc[-1])
    last_atr = atr_series.dropna()
    atr_pct = float(last_atr.iloc[-1]) / last_close if not last_atr.empty and last_close else None
    return fig, atr_pct


_PLAN_LINES = (
    ('Entry', '#2563EB', 'dot'),
    ('Stop', '#DC2626', 'dash'),
    ('Target', '#16A34A', 'dash'),
)


def _overlay_plan(fig: go.Figure, plan: dict | None) -> None:
    """Draw entry/stop/target reference lines on the price subplot."""
    if not plan:
        return
    for label, color, dash in _PLAN_LINES:
        level = plan.get(label)
        if level is None or pd.isna(level):
            continue
        fig.add_hline(
            y=float(level),
            line_dash=dash,
            line_color=color,
            line_width=1.2,
            annotation_text=f'{label} {_money(level)}',
            annotation_position='right',
            row=1,
            col=1,
        )


def _render_cache_controls(cache: SQLiteCache) -> None:
    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button('Refresh Cached Data'):
            cache.clear()
            st.success('Cache cleared. New requests will pull fresh data.')
    with col_b:
        stats = cache.stats()
        st.info(f"Cache entries: {stats['live']} live / {stats['total']} total")


def _render_sidebar(settings: Settings) -> tuple[FilterConfig, PortfolioConfig, ViewOptions]:
    st.sidebar.header('Screen Controls')
    min_confidence = st.sidebar.slider(
        'Min Confidence', min_value=0, max_value=100, value=45,
        help='Composite quality score for the setup (trend, RS, base, volume, reward).',
    )
    min_reward_risk = st.sidebar.slider(
        'Min Reward/Risk', min_value=1.0, max_value=5.0, value=1.5, step=0.1,
        help='Only keep setups whose target offers at least this multiple of the risk. '
             'Contractions run ~1.8R; pullbacks/breakouts project the full base move.',
    )
    min_volume = st.sidebar.number_input(
        'Min Average Volume', min_value=0, step=50_000, value=settings.min_avg_volume
    )
    selected_setups = st.sidebar.multiselect(
        'Setup Types', options=list(SETUP_OPTIONS), default=list(SETUP_OPTIONS)
    )
    rsi_period = st.sidebar.slider('Chart RSI Period', min_value=5, max_value=30, value=settings.rsi_period)

    st.sidebar.header('Portfolio')
    core_allocation = st.sidebar.slider(
        'Core Allocation', min_value=0.0, max_value=1.0, value=float(settings.core_allocation), step=0.05,
        help='Share of capital for the Core sleeve (durable trend-continuation leaders). '
             'The remainder funds the higher-octane Satellite sleeve.',
    )
    core_threshold = st.sidebar.slider(
        'Core Score Threshold', min_value=0.0, max_value=1.0, value=float(settings.core_score_threshold), step=0.05,
        help='Core-ness score at or above which a candidate joins the Core sleeve.',
    )
    max_position_weight = st.sidebar.slider(
        'Max Position Weight', min_value=0.02, max_value=0.25, value=float(settings.max_position_weight), step=0.01,
        help='Cap on any single name as a share of the whole book.',
    )

    sort_column = st.sidebar.selectbox('Sort By', SORTABLE_COLUMNS, index=SORTABLE_COLUMNS.index('Rank Score'))
    sort_desc = st.sidebar.checkbox('Sort Descending', value=True)
    default_page_index = (
        PAGE_SIZE_OPTIONS.index(settings.page_size_default)
        if settings.page_size_default in PAGE_SIZE_OPTIONS
        else 1
    )
    page_size = st.sidebar.selectbox('Rows per page', PAGE_SIZE_OPTIONS, index=default_page_index)
    run_scan = st.sidebar.button('Run Screen', type='primary')

    setups = tuple(selected_setups) if selected_setups else None
    config = replace(
        FilterConfig.from_settings(settings),
        min_confidence=float(min_confidence),
        min_reward_risk=float(min_reward_risk),
        min_avg_volume=int(min_volume),
        setups=setups,
    )
    portfolio = replace(
        PortfolioConfig.from_settings(settings),
        core_allocation=float(core_allocation),
        satellite_allocation=round(1.0 - float(core_allocation), 4),
        core_score_threshold=float(core_threshold),
        max_position_weight=float(max_position_weight),
    )
    view = ViewOptions(
        sort_column=sort_column,
        sort_desc=sort_desc,
        page_size=int(page_size),
        rsi_period=int(rsi_period),
        run_scan=run_scan,
    )
    return config, portfolio, view


def _maybe_run_screen(
    cache: SQLiteCache, engine: ScreenerEngine, config: FilterConfig, run_scan: bool
) -> None:
    if not run_scan and 'screen_df' in st.session_state:
        return
    with st.spinner('Fetching S&P 500 universe and screening symbols...'):
        universe = load_sp500_universe(cache)
        st.session_state['screen_df'] = engine.screen(universe, config=config)
        st.session_state['screen_at'] = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')


def _render_results(
    client: YahooFinanceClient, settings: Settings, engine: ScreenerEngine, view: ViewOptions
) -> None:
    screen_df = st.session_state.get('screen_df', pd.DataFrame())
    screen_at = st.session_state.get('screen_at', '-')

    st.subheader('Results')
    st.write(f'Last scan: {screen_at}')
    st.write(f'Matching symbols: {len(screen_df)}')

    if screen_df.empty:
        st.warning('No symbols matched the active filters.')
        return

    _render_sleeve_summary(screen_df)

    if view.sort_column in screen_df.columns:
        sorted_df = screen_df.sort_values(by=view.sort_column, ascending=not view.sort_desc)
    else:
        sorted_df = screen_df

    total_pages = max(math.ceil(len(sorted_df) / view.page_size), 1)
    page = st.number_input('Page', min_value=1, max_value=total_pages, value=1, step=1)
    start = (int(page) - 1) * view.page_size
    page_df = sorted_df.iloc[start:start + view.page_size].reset_index(drop=True)

    display_df = _prepare_display_df(page_df)
    st.dataframe(display_df, width='stretch', hide_index=True)

    st.download_button(
        label='Export Current Results to CSV',
        data=to_csv_bytes(sorted_df),
        file_name='stock_screener_results.csv',
        mime='text/csv',
    )


_SLEEVE_SUMMARY_FORMATTERS = {
    'Allocation %': _percent,
    'Portfolio Heat %': _percent,
    'Avg Confidence': _integer,
    'Avg R/R': _score,
    'Avg Core Score': _score,
}


def _render_sleeve_summary(screen_df: pd.DataFrame) -> None:
    if 'Sleeve' not in screen_df.columns:
        return
    summary = sleeve_summary(screen_df)
    st.markdown('**Portfolio sleeves (Core / Satellite)**')
    st.caption(
        'Suggested allocation plan: positions sized by risk parity within each '
        'sleeve, capped per name. Allocation % under 100% is held as cash; '
        'Portfolio Heat % is total capital at risk if every stop triggers.'
    )
    display = _apply_formatters(summary, _SLEEVE_SUMMARY_FORMATTERS)
    st.dataframe(display, width='stretch', hide_index=True)


def _chart_ticker_options(page_df: pd.DataFrame) -> list[str]:
    """Union of held, watchlist, recommended, and screened tickers (in that order)."""
    tickers: list[str] = []
    for key in ('monitor_df', 'watch_monitor', 'recommendations'):
        df = st.session_state.get(key)
        if isinstance(df, pd.DataFrame) and 'Ticker' in df.columns:
            tickers.extend(df['Ticker'].astype(str).tolist())
    if isinstance(page_df, pd.DataFrame) and 'Ticker' in page_df.columns:
        tickers.extend(page_df['Ticker'].astype(str).tolist())
    return list(dict.fromkeys(t for t in tickers if t))


def _lookup_plan_row(ticker: str) -> dict | None:
    """Find an existing analysis/result row for ``ticker`` in session state."""
    for key in ('positions_analysis', 'recommendations', 'screen_df'):
        df = st.session_state.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty and 'Ticker' in df.columns:
            match = df[df['Ticker'].astype(str) == ticker]
            if not match.empty:
                return match.iloc[0].to_dict()
    return None


def _chart_plan_row(engine: ScreenerEngine, ticker: str) -> dict | None:
    """Reuse a cached plan row if available, else analyze the ticker on demand."""
    row = _lookup_plan_row(ticker)
    if row is not None:
        return row
    universe = UniverseResult(tickers=[ticker], companies={})
    analysis = engine.analyze(universe, config=FilterConfig())
    if analysis is None or analysis.empty:
        return None
    return analysis.iloc[0].to_dict()


def _dash(text: str) -> str:
    return text if text else '\u2014'


def _render_chart_stats(row: dict, atr_pct: float | None) -> None:
    price = row.get('Price')
    stop = row.get('Stop')
    target = row.get('Target')
    to_stop = (
        (float(price) - float(stop)) / float(price)
        if price and stop and not pd.isna(price) and not pd.isna(stop) and float(price) > 0
        else None
    )
    to_target = (
        (float(target) - float(price)) / float(price)
        if price and target and not pd.isna(price) and not pd.isna(target) and float(price) > 0
        else None
    )
    setup = row.get('Setup')
    st.markdown('**Setup & trade plan**')
    r1 = st.columns(4)
    r1[0].metric('Setup', _dash(str(setup)) if setup is not None else '\u2014')
    r1[1].metric('Confidence', _dash(_integer(row.get('Confidence'))))
    r1[2].metric('R/R', _dash(_score(row.get('R/R'))))
    r1[3].metric('Trend score', _dash(_score(row.get('Trend Score'))))
    r2 = st.columns(4)
    r2[0].metric('RS vs SPX', _dash(_percent(row.get('RS Outperformance'))))
    r2[1].metric('Rel volume', _dash(_multiple(row.get('Rel Volume'))))
    r2[2].metric('ATR %', _dash(_percent(atr_pct)))
    r2[3].metric('Market context', _dash(str(row.get('Market Context') or '')))
    r3 = st.columns(4)
    r3[0].metric('Entry', _dash(_money(row.get('Entry'))))
    r3[1].metric('Stop', _dash(_money(row.get('Stop'))), _dash(_percent(to_stop)), delta_color='off')
    r3[2].metric(
        'Target', _dash(_money(row.get('Target'))), _dash(_percent(to_target)), delta_color='off'
    )
    actionable = row.get('Actionable')
    if actionable is not None:
        r3[3].metric('Actionable', 'Yes' if bool(actionable) else 'No')


def _render_chart_section(
    client: YahooFinanceClient,
    settings: Settings,
    engine: ScreenerEngine,
    page_df: pd.DataFrame,
    rsi_period: int,
) -> None:
    st.subheader('Ticker Chart')
    st.caption(
        'Chart any symbol — your holdings, watchlist, recommendations, screened '
        'names, or a free-text ticker. Trade-plan levels overlay when a plan exists.'
    )
    options = _chart_ticker_options(page_df)
    col_free, col_pick, col_period = st.columns([1, 1, 1])
    free_text = col_free.text_input('Any ticker', value='', help='Overrides the dropdown.')
    picked = col_pick.selectbox(
        'Or pick from your lists', options=options, index=0
    ) if options else None
    chart_period = col_period.selectbox('Period', CHART_PERIODS, index=CHART_PERIODS.index('1y'))

    ticker = free_text.strip().upper() or (picked or '')
    if not ticker:
        st.info('Enter a ticker or run a screen to populate the dropdown.')
        return

    plan_row = _chart_plan_row(engine, ticker)
    plan = plan_row if plan_row else None
    fig, atr_pct = _build_chart(
        client, settings, ticker=ticker, period=chart_period, rsi_period=rsi_period, plan=plan
    )
    if fig is None:
        st.warning(f'No chart data available for {ticker}.')
        return
    st.plotly_chart(fig, width='stretch')
    if plan_row:
        _render_chart_stats(plan_row, atr_pct)
    else:
        st.caption(f'No trade plan for {ticker} (no computable setup).')


_BACKTEST_STATS_FORMATTERS = {
    'Win Rate': _percent_int,
    'Expectancy (R)': _r_multiple,
    'Avg Win (R)': _r_multiple,
    'Avg Loss (R)': _r_multiple,
    'Profit Factor': _score,
    'Avg Bars Held': _integer,
}


def _format_stats_df(df: pd.DataFrame) -> pd.DataFrame:
    return _apply_formatters(df, _BACKTEST_STATS_FORMATTERS)


_MONITOR_FORMATTERS = {
    'Price': _money,
    'EMA20': _money,
    'SMA50': _money,
    'SMA200': _money,
    '% vs EMA20': _percent,
    '% vs SMA50': _percent,
    '% vs SMA200': _percent,
    'Entry': _money,
    'Unreal P&L %': _percent,
    'Shares': _integer,
    'Value': _money,
    'Weight %': _percent,
    'Unreal P&L $': _money,
}

_POSITIONS_PLACEHOLDER = (
    '# One ticker per line. Optionally add entry price and shares.\n'
    '# Format: TICKER, entry_price, shares   (price and shares optional)\n'
    '# Group positions by account with a [Section] header.\n'
    '# Repeat a ticker per lot to average the cost basis.\n'
    '#\n'
    '# [Taxable]\n'
    '# AAPL, 150, 10\n'
    '# AAPL, 170, 20\n'
    '# MSFT, 410.50\n'
    '#\n'
    '# [Roth IRA]\n'
    '# NVDA, 95.20, 100\n'
)

# Persistent, private list of the user's positions. Git-ignored so real
# holdings never get committed; auto-loaded into the app on every start.
POSITIONS_FILE = Path(__file__).resolve().parents[1] / 'positions.txt'

# Committed companions: portfolio composition (tickers + sleeve, no sizes) and
# the watchlist of names we follow but do not (yet) hold.
PORTFOLIO_FILE = Path(__file__).resolve().parents[1] / 'portfolio.txt'
WATCHLIST_FILE = Path(__file__).resolve().parents[1] / 'watchlist.txt'


def _initial_positions_text() -> str:
    if POSITIONS_FILE.exists():
        return POSITIONS_FILE.read_text(encoding='utf-8')
    return _POSITIONS_PLACEHOLDER


def _reload_positions_input() -> None:
    """Refresh the positions editor from disk (runs before widget re-instantiation)."""
    st.session_state['positions_input'] = _initial_positions_text()


def _read_file_text(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''


def _watchlist_tickers() -> list[str]:
    """Tickers from the committed watchlist (sleeve tags, if any, ignored)."""
    entries = parse_portfolio(_read_file_text(WATCHLIST_FILE))
    return [entry.ticker for entry in entries]


def _etf_tickers(client: YahooFinanceClient, tickers: list[str]) -> set[str]:
    """Return the subset of ``tickers`` Yahoo classifies as funds (ETF/MUTUALFUND).

    Used to exclude funds from the individual-stock diversification cap. Unknown
    quote types fall back to treating the name as a stock (not in the set).
    """
    if not tickers:
        return set()
    fundamentals = client.fetch_fundamentals(tickers)
    funds = {'ETF', 'MUTUALFUND'}
    return {
        t for t, f in fundamentals.items()
        if (f.quote_type or '').upper() in funds
    }


def _render_concentration(monitor: pd.DataFrame, title: str = 'Concentration') -> None:
    stats = concentration_summary(monitor)
    if stats is None:
        return
    st.markdown(f'**{title}**')
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Positions', stats.positions)
    c2.metric(
        'Largest position',
        _percent(stats.largest_weight),
        help=f'{stats.largest_ticker} is your biggest holding.',
    )
    c3.metric(f'Top {min(stats.positions, 5)} weight', _percent(stats.top_n_weight))
    c4.metric(
        'Effective holdings',
        f'{stats.effective_positions:.1f}',
        help='Equal-weight-equivalent count (1 / HHI). Far below your actual '
             'position count means a few names dominate.',
    )
    message = (
        f'{stats.label} (HHI {stats.hhi:.2f}). Largest: {stats.largest_ticker} '
        f'at {_percent(stats.largest_weight)}; top {min(stats.positions, 5)} '
        f'hold {_percent(stats.top_n_weight)} of the book.'
    )
    if stats.label == 'Diversified':
        st.success(message)
    elif stats.label == 'Moderately concentrated':
        st.warning(message)
    else:
        st.error(message)


def _render_accounts(monitor: pd.DataFrame) -> None:
    """Per-account value, P&L, and concentration breakdown."""
    st.markdown('**By account**')
    for label, sub in account_groups(monitor):
        held = sub['Value'].dropna()
        with st.expander(f'{label} \u2014 {len(sub)} position(s)', expanded=True):
            if not held.empty:
                c1, c2 = st.columns(2)
                c1.metric('Account value', _money(float(held.sum())))
                pnl = sub['Unreal P&L $'].dropna()
                c2.metric('Account P&L', _money(float(pnl.sum())) if not pnl.empty else '\u2014')
            _render_concentration(sub)


def _render_positions(
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

    if 'positions_input' not in st.session_state:
        st.session_state['positions_input'] = _initial_positions_text()
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
                POSITIONS_FILE.write_text(text, encoding='utf-8')
                st.success(f'Saved your sizes to {POSITIONS_FILE.name}.')
        with col_reload:
            st.button(
                f'Reload from {POSITIONS_FILE.name}',
                on_click=_reload_positions_input,
                help='Re-read positions.txt from disk (discards unsaved edits here).',
            )
    text = st.session_state['positions_input']

    directive_value = parse_account_value(text)
    fallback_value = float(st.session_state.get('positions_portfolio_value', 0.0) or 0.0)
    default_value = float(directive_value) if directive_value else fallback_value
    account_value = st.number_input(
        'Account value ($)',
        min_value=0.0,
        value=default_value,
        step=1000.0,
        help='Drives 1%-risk add sizing and allocation. Prefilled from the '
             '"account_value" directive in positions.txt (falls back to your total '
             'position value); override here if needed.',
    )

    if st.button('Analyze Positions', type='primary'):
        portfolio_entries = parse_portfolio(_read_file_text(PORTFOLIO_FILE))
        position_entries = parse_positions(text)
        merged = merge_holdings(portfolio_entries, position_entries)
        if not merged:
            st.session_state.pop('monitor_df', None)
            st.warning('No holdings found. Add tickers to portfolio.txt or positions.txt.')
        else:
            held = [entry.ticker for entry in merged]
            held_set = set(held)
            watch = [t for t in _watchlist_tickers() if t not in held_set]
            all_tickers = held + watch
            with st.spinner(f'Analyzing {len(all_tickers)} symbol(s)...'):
                history = client.fetch_history(all_tickers, period='2y')
                monitor = build_monitor(merged, history, settings)
                watch_entries = [PositionEntry(t, sleeve=SATELLITE) for t in watch]
                watch_monitor = build_monitor(watch_entries, history, settings)
                universe = UniverseResult(tickers=all_tickers, companies={})
                analysis = engine.analyze(universe, config=config)
                etfs = _etf_tickers(client, all_tickers)
            st.session_state['monitor_df'] = monitor
            st.session_state['watch_monitor'] = watch_monitor
            st.session_state['positions_analysis'] = analysis
            st.session_state['positions_etfs'] = etfs
            st.session_state['positions_account_value'] = account_value
            st.session_state['merged_entries'] = merged
            st.session_state['positions_portfolio_value'] = float(
                monitor['Value'].dropna().sum()
            )

    monitor = st.session_state.get('monitor_df')
    if monitor is None:
        return
    if 'Sleeve' not in monitor.columns:
        # Stale monitor from an earlier app version (session survives reloads).
        st.info('Your positions view is out of date. Click "Analyze Positions" to refresh.')
        return

    analysis = st.session_state.get('positions_analysis', pd.DataFrame())
    watch_monitor = st.session_state.get('watch_monitor', pd.DataFrame())
    etfs = st.session_state.get('positions_etfs', set())
    account_value = st.session_state.get('positions_account_value', account_value)
    merged = st.session_state.get('merged_entries', [])
    lookup = _analysis_lookup(analysis)

    held_value = monitor['Value'].dropna()
    if not held_value.empty:
        c1, c2 = st.columns(2)
        c1.metric('Portfolio value', _money(float(held_value.sum())))
        c2.metric('Unrealized P&L', _money(float(monitor['Unreal P&L $'].dropna().sum())))

    core_tab, sat_tab, watch_tab = st.tabs(['Core', 'Satellite', 'Watchlist'])
    with core_tab:
        _render_core_panel(monitor)
    with sat_tab:
        _render_satellite_panel(monitor, lookup, account_value, settings)
    with watch_tab:
        _render_watchlist_panel(watch_monitor, lookup, account_value, settings)

    _render_allocation_panel(monitor, etfs, settings)
    _render_risk_panel(monitor, lookup, account_value)

    if has_accounts(monitor):
        _render_accounts(monitor)
        _render_concentration(monitor, title='Overall concentration')
    else:
        _render_concentration(monitor)

    _render_publish_button(merged)


_CORE_DISPLAY_COLUMNS = (
    'Ticker', 'Account', 'Price', '% vs SMA50', '% vs SMA200', 'Trend',
    'Signal', '50/200 Cross', 'Value', 'Weight %', 'Unreal P&L %', 'Unreal P&L $',
)

_PLAN_FORMATTERS = {
    'Price': _money,
    'Entry': _money,
    'Stop': _money,
    'Target': _money,
    'R/R': _score,
    'Confidence': _integer,
    'Shares': _integer,
    'Value': _money,
    'Weight %': _percent,
    'Unreal P&L %': _percent,
    'Add Shares': _integer,
    'Add $': _money,
}


def _analysis_lookup(analysis: pd.DataFrame) -> dict[str, dict]:
    if analysis is None or analysis.empty:
        return {}
    return {str(row['Ticker']): row.to_dict() for _, row in analysis.iterrows()}


def _is_core(sleeve) -> bool:
    return str(sleeve).lower() == CORE


def _render_core_panel(monitor: pd.DataFrame) -> None:
    core = monitor[monitor['Sleeve'].map(_is_core)]
    st.caption('Long-term anchors (e.g. VTI / VXUS) \u2014 monitored, not traded.')
    if core.empty:
        st.info('No core holdings tagged in portfolio.txt.')
        return
    columns = [c for c in _CORE_DISPLAY_COLUMNS if c in core.columns]
    display = core[columns]
    if not has_accounts(monitor):
        display = display.drop(columns=['Account'], errors='ignore')
    st.dataframe(_apply_formatters(display, _MONITOR_FORMATTERS), width='stretch', hide_index=True)


def _add_sizing(account_value: float, settings: Settings, analysis_row: dict, current_value: float):
    entry = analysis_row.get('Entry')
    stop = analysis_row.get('Stop')
    if account_value <= 0 or entry is None or stop is None or pd.isna(entry) or pd.isna(stop):
        return None
    return suggest_add_size(
        account_value,
        settings.risk_per_trade,
        float(entry),
        float(stop),
        current_value=float(current_value),
        max_position_weight=settings.max_position_weight,
    )


def _satellite_action(monitor_row, analysis_row: dict, sizing, actionable: bool) -> str:
    price = monitor_row['Price']
    stop = analysis_row.get('Stop')
    vs_sma200 = monitor_row.get('% vs SMA200')
    vs_ema20 = monitor_row.get('% vs EMA20')
    if price is not None and stop is not None and not pd.isna(stop) and float(price) < float(stop):
        return 'Stop breached'
    if vs_sma200 is not None and not pd.isna(vs_sma200) and float(vs_sma200) < 0:
        return 'Trend broke'
    if actionable and sizing is not None and sizing.shares > 0:
        entry = analysis_row.get('Entry')
        return f'Add near {_money(entry)}' if entry is not None else 'Add'
    if vs_ema20 is not None and not pd.isna(vs_ema20) and float(vs_ema20) > 0.10:
        return 'Extended'
    return 'Hold'


def _render_satellite_panel(
    monitor: pd.DataFrame, lookup: dict, account_value: float, settings: Settings
) -> None:
    sat = monitor[~monitor['Sleeve'].map(_is_core)]
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
        sizing = _add_sizing(account_value, settings, a, current_value)
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
            'Add Shares': sizing.shares if sizing else None,
            'Add $': sizing.dollars if sizing else None,
            'Action': _satellite_action(r, a, sizing, actionable),
        }
        if not has_acct:
            row.pop('Account')
        rows.append(row)
    frame = pd.DataFrame(rows)
    st.dataframe(_apply_formatters(frame, _PLAN_FORMATTERS), width='stretch', hide_index=True)


def _render_watchlist_panel(
    watch_monitor: pd.DataFrame, lookup: dict, account_value: float, settings: Settings
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
        sizing = _add_sizing(account_value, settings, a, current_value=0.0)
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
    st.dataframe(_apply_formatters(frame, _PLAN_FORMATTERS), width='stretch', hide_index=True)


def _render_allocation_panel(monitor: pd.DataFrame, etfs: set, settings: Settings) -> None:
    st.markdown('**Allocation vs target**')
    stats = allocation_summary(monitor, settings.core_allocation_min, settings.core_allocation_max)
    if stats is None:
        st.info('Add share counts to your positions to see Core/Satellite allocation.')
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric(
            'Core',
            _percent(stats.core_pct),
            help=f'Target {_percent(stats.target_min)}\u2013{_percent(stats.target_max)}.',
        )
        c2.metric('Satellite', _percent(stats.satellite_pct))
        c3.metric('Total value', _money(stats.total_value))
        message = (
            f'Core {_percent(stats.core_pct)} vs target '
            f'{_percent(stats.target_min)}\u2013{_percent(stats.target_max)} \u2014 {stats.label}.'
        )
        if stats.within_band:
            st.success(message)
        else:
            st.warning(message)

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
        if _is_core(r['Sleeve']):
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
    c1.metric('Open risk ($)', _money(total_risk))
    if account_value > 0:
        c2.metric('Open risk (% of account)', _percent(total_risk / account_value))
    st.caption(
        'Capital lost if every satellite hit its stop today '
        '(\u03a3 shares \u00d7 (price \u2212 stop)). Core holdings are excluded.'
    )


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
            PORTFOLIO_FILE.write_text(manifest, encoding='utf-8')
            st.success(f'Wrote composition to {PORTFOLIO_FILE.name}.')
    with col2:
        st.download_button(
            'Download portfolio.txt',
            data=manifest,
            file_name='portfolio.txt',
            mime='text/plain',
        )


_REC_FORMATTERS = {
    'Confidence': _integer,
    'R/R': _score,
    'Entry': _money,
    'Stop': _money,
    'Target': _money,
    'Rank Score': _score,
    'Add Shares': _integer,
    'Add $': _money,
}


def _held_tickers() -> set[str]:
    """Tickers already held (committed composition merged with private sizes)."""
    merged = st.session_state.get('merged_entries')
    if merged:
        return {entry.ticker for entry in merged}
    portfolio_entries = parse_portfolio(_read_file_text(PORTFOLIO_FILE))
    position_entries = parse_positions(_read_file_text(POSITIONS_FILE))
    return {entry.ticker for entry in merge_holdings(portfolio_entries, position_entries)}


def _individual_cap_state(settings: Settings) -> tuple[bool, str]:
    """Whether the individual-stock count is at/over the diversification cap."""
    monitor = st.session_state.get('monitor_df')
    if monitor is None or 'Sleeve' not in monitor.columns:
        return False, ''
    etfs = st.session_state.get('positions_etfs', set())
    count = count_individual_stocks(monitor, etfs)
    cap = settings.max_individual_stocks
    if count >= cap:
        return True, (
            f'At max individual holdings ({count}/{cap}) \u2014 consider rotating rather '
            'than adding. Single-stock picks are de-emphasized below; fund picks still shown.'
        )
    return False, ''


def _recommendation_rows(
    recs: pd.DataFrame, account_value: float, settings: Settings, etfs: set
) -> pd.DataFrame:
    rows = []
    for _, r in recs.iterrows():
        ticker = str(r['Ticker'])
        sizing = _add_sizing(account_value, settings, r.to_dict(), current_value=0.0)
        rows.append({
            'Ticker': ticker,
            'Company': r.get('Company Name'),
            'Setup': r.get('Setup'),
            'Type': 'ETF' if ticker in etfs else 'Stock',
            'Confidence': r.get('Confidence'),
            'R/R': r.get('R/R'),
            'Entry': r.get('Entry'),
            'Stop': r.get('Stop'),
            'Target': r.get('Target'),
            'Rank Score': r.get('Rank Score'),
            'Add Shares': sizing.shares if sizing else None,
            'Add $': sizing.dollars if sizing else None,
        })
    return pd.DataFrame(rows)


def _render_recommendations(
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

    if st.button('Find recommended adds', type='primary'):
        with st.spinner('Screening S&P 500 + watchlist for high-conviction setups...'):
            universe = load_sp500_universe(cache)
            watch = _watchlist_tickers()
            tickers = list(dict.fromkeys([*universe.tickers, *watch]))
            rec_universe = UniverseResult(tickers=tickers, companies=dict(universe.companies))
            rec_config = FilterConfig(
                min_confidence=float(min_conf),
                min_reward_risk=float(min_rr),
                min_avg_volume=settings.min_avg_volume,
            )
            recs = engine.screen(rec_universe, config=rec_config)
            held = _held_tickers()
            if not recs.empty and held:
                recs = recs[~recs['Ticker'].isin(held)]
            recs = recs.sort_values('Rank Score', ascending=False).reset_index(drop=True)
            etfs = _etf_tickers(client, list(recs['Ticker'])) if not recs.empty else set()
        st.session_state['recommendations'] = recs
        st.session_state['recommendation_etfs'] = etfs
        st.session_state['recommendation_at'] = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')

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
    table = _recommendation_rows(recs, account_value, settings, etfs)

    at_cap, cap_note = _individual_cap_state(settings)
    if at_cap:
        st.warning(cap_note)
        etf_picks = table[table['Type'] == 'ETF']
        stock_picks = table[table['Type'] == 'Stock']
        if not etf_picks.empty:
            st.markdown('**Fund picks (allowed)**')
            st.dataframe(
                _apply_formatters(etf_picks, _REC_FORMATTERS), width='stretch', hide_index=True
            )
        if not stock_picks.empty:
            st.markdown('**Single-stock picks (rotate, don\u2019t add)**')
            st.dataframe(
                _apply_formatters(stock_picks, _REC_FORMATTERS), width='stretch', hide_index=True
            )
    else:
        st.dataframe(_apply_formatters(table, _REC_FORMATTERS), width='stretch', hide_index=True)
        if account_value <= 0:
            st.caption('Set your account value under My Positions to see risk-based add sizes.')


def _render_backtest(cache: SQLiteCache, engine: ScreenerEngine) -> None:
    st.caption(
        'Replays the same setup/plan logic across ~2 years of daily bars with no '
        'look-ahead, then measures realized R-multiples. Daily-bar simulation with '
        'no slippage/commissions on a survivorship-biased universe \u2014 read the '
        'numbers as relative comparisons, not a profitability claim.'
    )

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        max_symbols = st.number_input('Symbols to test', min_value=5, max_value=500, value=50, step=5)
    with col_b:
        min_confidence = st.slider('Min confidence', min_value=0, max_value=100, value=50, key='bt_conf')
    with col_c:
        max_holding = st.slider('Max holding (bars)', min_value=10, max_value=120, value=40)
    run_backtest = st.button('Run Backtest')

    if run_backtest:
        params = BacktestParams(min_confidence=float(min_confidence), max_holding_bars=int(max_holding))
        with st.spinner(f'Replaying history for up to {int(max_symbols)} symbols...'):
            universe = load_sp500_universe(cache)
            trades = engine.backtest(universe, params, max_symbols=int(max_symbols))
        st.session_state['backtest_trades'] = trades

    trades = st.session_state.get('backtest_trades')
    if trades is None:
        return
    if not trades:
        st.warning('No trades were generated. Try lowering the minimum confidence.')
        return

    overall = summarize(trades)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric('Trades', overall.trades)
    m2.metric('Win Rate', f'{overall.win_rate * 100:.0f}%')
    m3.metric('Expectancy', f'{overall.expectancy:+.2f}R')
    m4.metric('Profit Factor', _score(overall.profit_factor))

    st.markdown('**By setup type**')
    st.dataframe(_format_stats_df(stats_to_frame(summarize_by_setup(trades))), width='stretch', hide_index=True)

    st.markdown('**By confidence tier**')
    st.dataframe(_format_stats_df(stats_to_frame(summarize_by_confidence(trades))), width='stretch', hide_index=True)

    trades_df = trades_to_frame(trades)
    st.download_button(
        label='Export Backtest Trades to CSV',
        data=trades_df.to_csv(index=False).encode('utf-8'),
        file_name='backtest_trades.csv',
        mime='text/csv',
    )


def run() -> None:
    settings, cache, client, engine = get_services()

    st.title('Position Manager & S&P 500 Screener')
    st.caption(
        'Track your holdings, size adds by risk, surface high-conviction setups, '
        'and chart any name — powered by Yahoo Finance data with daily caching.'
    )

    _render_cache_controls(cache)
    config, portfolio, view = _render_sidebar(settings)
    engine.portfolio = portfolio
    _maybe_run_screen(cache, engine, config, view.run_scan)
    _render_positions(client, settings, engine, config)
    _render_recommendations(cache, client, settings, engine)
    _render_chart_section(
        client, settings, engine, st.session_state.get('screen_df', pd.DataFrame()), view.rsi_period
    )
    with st.expander('Full S&P 500 screen', expanded=False):
        _render_results(client, settings, engine, view)
    with st.expander('Backtest (historical performance)', expanded=False):
        _render_backtest(cache, engine)


if __name__ == '__main__':
    run()
