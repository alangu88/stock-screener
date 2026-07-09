"""Ticker chart section: candlesticks + MAs, RSI, volume, and plan overlays."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.analysis.indicators import atr, compute_indicators
from src.config import Settings
from src.data.universe import UniverseResult
from src.data.yahoo_client import YahooFinanceClient
from src.screener.engine import FilterConfig, ScreenerEngine
from src.ui.formatting import dash, integer, money, multiple, percent, score

CHART_PERIODS = ['1mo', '3mo', '6mo', '1y', '2y', '5y']

_PLAN_LINES = (
    ('Entry', '#2563EB', 'dot'),
    ('Stop', '#DC2626', 'dash'),
    ('Target', '#16A34A', 'dash'),
)


def render_chart_section(
    client: YahooFinanceClient,
    settings: Settings,
    engine: ScreenerEngine,
    rsi_period: int,
) -> None:
    st.subheader('Ticker Chart')
    st.caption(
        'Chart any symbol — your holdings, watchlist, recommendations, or a '
        'free-text ticker. Trade-plan levels overlay when a plan exists.'
    )
    options = _ticker_options()
    col_free, col_pick, col_period = st.columns([1, 1, 1])
    free_text = col_free.text_input(
        'Any ticker', key='chart_free_text', help='Overrides the dropdown.'
    )
    picked = col_pick.selectbox(
        'Or pick from your lists', options=options, key='chart_pick'
    ) if options else None
    chart_period = col_period.selectbox(
        'Period', CHART_PERIODS, index=CHART_PERIODS.index('1y'), key='chart_period'
    )

    ticker = free_text.strip().upper() or (picked or '')
    if not ticker:
        st.info('Enter a ticker, or run the screen to populate the dropdown.')
        return

    plan_row = _plan_row(engine, ticker)
    fig, atr_pct = _build_chart(
        client, settings, ticker=ticker, period=chart_period, rsi_period=rsi_period, plan=plan_row
    )
    if fig is None:
        st.warning(f'No chart data available for {ticker}.')
        return
    st.plotly_chart(fig, width='stretch')
    if plan_row:
        _render_chart_stats(plan_row, atr_pct)
    else:
        st.caption(f'No trade plan for {ticker} (no computable setup).')


def _ticker_options() -> list[str]:
    """Tickers from the latest screen results plus the watchlist file."""
    from src.ui.files import watchlist_tickers

    tickers: list[str] = []
    df = st.session_state.get('screen_results')
    if isinstance(df, pd.DataFrame) and 'Ticker' in df.columns:
        tickers.extend(df['Ticker'].astype(str).tolist())
    tickers.extend(watchlist_tickers())
    return list(dict.fromkeys(t for t in tickers if t))


def _plan_row(engine: ScreenerEngine, ticker: str) -> dict | None:
    """Reuse a cached plan row if available, else analyze the ticker on demand."""
    df = st.session_state.get('screen_results')
    if isinstance(df, pd.DataFrame) and not df.empty and 'Ticker' in df.columns:
        match = df[df['Ticker'].astype(str) == ticker]
        if not match.empty:
            return match.iloc[0].to_dict()
    universe = UniverseResult(tickers=[ticker], companies={})
    analysis = engine.analyze(universe, config=FilterConfig())
    if analysis is None or analysis.empty:
        return None
    return analysis.iloc[0].to_dict()


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


def _overlay_plan(fig: go.Figure, plan: dict | None) -> None:
    """Draw entry/stop/target reference lines on the price subplot."""
    if not plan:
        return
    for label, color, dash_style in _PLAN_LINES:
        level = plan.get(label)
        if level is None or pd.isna(level):
            continue
        fig.add_hline(
            y=float(level),
            line_dash=dash_style,
            line_color=color,
            line_width=1.2,
            annotation_text=f'{label} {money(level)}',
            annotation_position='right',
            row=1,
            col=1,
        )


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
    r1[0].metric('Setup', dash(str(setup)) if setup is not None else dash(''))
    r1[1].metric('Confidence', dash(integer(row.get('Confidence'))))
    r1[2].metric('R/R', dash(score(row.get('R/R'))))
    r1[3].metric('Trend score', dash(score(row.get('Trend Score'))))
    r2 = st.columns(4)
    r2[0].metric('RS vs SPX', dash(percent(row.get('RS Outperformance'))))
    r2[1].metric('Rel volume', dash(multiple(row.get('Rel Volume'))))
    r2[2].metric('ATR %', dash(percent(atr_pct)))
    r2[3].metric('Market context', dash(str(row.get('Market Context') or '')))
    r3 = st.columns(4)
    r3[0].metric('Entry', dash(money(row.get('Entry'))))
    r3[1].metric('Stop', dash(money(row.get('Stop'))), dash(percent(to_stop)), delta_color='off')
    r3[2].metric(
        'Target', dash(money(row.get('Target'))), dash(percent(to_target)), delta_color='off'
    )
    actionable = row.get('Actionable')
    if actionable is not None:
        r3[3].metric('Actionable', 'Yes' if bool(actionable) else 'No')
