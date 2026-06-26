from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.analysis.indicators import compute_indicators
from src.config import Settings, load_settings
from src.data.cache import SQLiteCache
from src.data.universe import load_sp500_universe
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
from src.screener.portfolio import PortfolioConfig, sleeve_summary
from src.screener.result import SORTABLE_COLUMNS
from src.screener.setups import BREAKOUT, CONTRACTION, PULLBACK
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
) -> go.Figure | None:
    history_map = client.fetch_history([ticker], period=period, interval='1d')
    df = history_map.get(ticker, pd.DataFrame()).copy()
    if df.empty:
        return None

    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    if any(col not in df.columns for col in required_cols):
        return None

    chart_df = df[required_cols].dropna(subset=['Open', 'High', 'Low', 'Close']).copy()
    if chart_df.empty:
        return None

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
    fig.update_yaxes(title_text='Price', row=1, col=1)
    fig.update_yaxes(title_text='RSI', row=2, col=1, range=[0, 100])
    fig.update_yaxes(title_text='Volume', row=3, col=1)
    return fig


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


def _render_results(client: YahooFinanceClient, settings: Settings, view: ViewOptions) -> None:
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

    _render_chart_section(client, settings, page_df, view.rsi_period)


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


def _render_chart_section(
    client: YahooFinanceClient, settings: Settings, page_df: pd.DataFrame, rsi_period: int
) -> None:
    st.subheader('Ticker Chart')
    ticker = st.selectbox('Select ticker', options=page_df['Ticker'].tolist(), index=0)
    chart_period = st.selectbox('Chart period', CHART_PERIODS, index=CHART_PERIODS.index('1y'))
    fig = _build_chart(client, settings, ticker=ticker, period=chart_period, rsi_period=rsi_period)
    if fig is None:
        st.warning(f'No chart data available for {ticker}.')
        return
    st.plotly_chart(fig, width='stretch')


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


def _render_backtest(cache: SQLiteCache, engine: ScreenerEngine) -> None:
    st.subheader('Backtest (Historical Performance)')
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

    st.title('S&P 500 Stock Screener')
    st.caption('NYSE/NASDAQ/AMEX focus using Yahoo Finance data and daily caching')

    _render_cache_controls(cache)
    config, portfolio, view = _render_sidebar(settings)
    engine.portfolio = portfolio
    _maybe_run_screen(cache, engine, config, view.run_scan)
    _render_results(client, settings, view)
    _render_backtest(cache, engine)


if __name__ == '__main__':
    run()
