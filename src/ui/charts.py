"""Ticker chart section: candlesticks + MAs, RSI, volume, and plan overlays."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.analysis.indicators import atr, compute_indicators
from src.config import Settings
from src.core.scoring import EntryQualityScorer
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
    picked = (
        col_pick.selectbox('Or pick from your lists', options=options, key='chart_pick')
        if options
        else None
    )
    chart_period = col_period.selectbox(
        'Period', CHART_PERIODS, index=CHART_PERIODS.index('1y'), key='chart_period'
    )

    ticker = free_text.strip().upper() or (picked or '')
    if not ticker:
        st.info('Enter a ticker, or run the screen to populate the dropdown.')
        return

    plan_row = _plan_row(engine, ticker)
    default_entry = (
        float(plan_row.get('Entry')) if plan_row and plan_row.get('Entry') is not None else 0.0
    )
    default_stop = (
        float(plan_row.get('Stop')) if plan_row and plan_row.get('Stop') is not None else 0.0
    )
    default_exit = (
        float(plan_row.get('Target')) if plan_row and plan_row.get('Target') is not None else 0.0
    )
    entry_col, stop_col, exit_col, label_col = st.columns([1, 1, 1, 1.5])
    custom_entry = entry_col.number_input(
        'Entry',
        min_value=0.0,
        value=default_entry,
        step=0.01,
        format='%.2f',
        help='Entry price to annotate on the chart for this ticker.',
    )
    custom_stop = stop_col.number_input(
        'Stop',
        min_value=0.0,
        value=default_stop,
        step=0.01,
        format='%.2f',
        help='Stop-loss price to annotate on the chart for this ticker.',
    )
    custom_exit = exit_col.number_input(
        'Exit',
        min_value=0.0,
        value=default_exit,
        step=0.01,
        format='%.2f',
        help='Exit/target price to annotate on the chart for this ticker.',
    )
    show_labels = label_col.checkbox('Show trade labels', value=True)

    fig, atr_pct = _build_chart(
        client,
        settings,
        ticker=ticker,
        period=chart_period,
        rsi_period=rsi_period,
        plan=plan_row,
        custom_entry=custom_entry if show_labels and custom_entry > 0 else None,
        custom_stop=custom_stop if show_labels and custom_stop > 0 else None,
        custom_exit=custom_exit if show_labels and custom_exit > 0 else None,
    )
    if fig is None:
        st.warning(f'No chart data available for {ticker}.')
        return
    current_price = None
    if fig.data:
        last_trace = fig.data[0]
        if hasattr(last_trace, 'close') and hasattr(last_trace.close, '__len__'):
            close_values = last_trace.close
            if len(close_values):
                current_price = float(close_values[-1])
    _render_trade_legend(
        plan_row,
        current_price=current_price,
        custom_entry=custom_entry,
        custom_stop=custom_stop,
        custom_exit=custom_exit,
    )
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
    custom_entry: float | None = None,
    custom_stop: float | None = None,
    custom_exit: float | None = None,
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

    current_price = float(chart_df['Close'].iloc[-1])
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
    chart_df['CCI'] = indicators.get('CCI', pd.Series(0.0, index=chart_df.index))
    chart_df['MACD'] = indicators.get('MACD', pd.Series(0.0, index=chart_df.index))
    chart_df['MACD_SIGNAL'] = indicators.get('MACD_SIGNAL', pd.Series(0.0, index=chart_df.index))
    chart_df['MACD_HIST'] = indicators.get('MACD_HIST', pd.Series(0.0, index=chart_df.index))
    chart_df['VOL_AVG'] = indicators['VOL_AVG']

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.52, 0.16, 0.16, 0.16],
        subplot_titles=(f'{ticker} Price', 'Momentum', 'Volume', 'Indicators'),
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
        go.Scatter(
            x=chart_df.index,
            y=chart_df['EMA'],
            mode='lines',
            name=f'EMA {ema_w}',
            line=dict(color='#0284C7', width=1.5),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=chart_df.index,
            y=chart_df['SMA_SHORT'],
            mode='lines',
            name=f'SMA {short_w}',
            line=dict(color='#16A34A', width=1.5),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=chart_df.index,
            y=chart_df['SMA_LONG'],
            mode='lines',
            name=f'SMA {long_w}',
            line=dict(color='#B45309', width=1.5),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=chart_df.index,
            y=chart_df['RSI'],
            mode='lines',
            name='RSI',
            line=dict(color='#7C2D12', width=1.5),
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=chart_df.index,
            y=chart_df['CCI'],
            mode='lines',
            name='CCI',
            line=dict(color='#7C3AED', width=1.5),
        ),
        row=2,
        col=1,
    )
    fig.add_hline(y=70, line_dash='dash', line_color='#DC2626', row=2, col=1)
    fig.add_hline(y=30, line_dash='dash', line_color='#059669', row=2, col=1)
    fig.add_hline(y=100, line_dash='dot', line_color='#8B5CF6', row=2, col=1)
    fig.add_hline(y=-100, line_dash='dot', line_color='#8B5CF6', row=2, col=1)

    fig.add_trace(
        go.Bar(
            x=chart_df.index,
            y=chart_df['Volume'],
            name='Volume',
            marker_color='#64748B',
            opacity=0.55,
        ),
        row=3,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=chart_df.index,
            y=chart_df['VOL_AVG'],
            mode='lines',
            name='Vol Avg 20',
            line=dict(color='#334155', width=1.5),
        ),
        row=3,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=chart_df.index,
            y=chart_df['MACD'],
            mode='lines',
            name='MACD',
            line=dict(color='#0EA5E9', width=1.5),
        ),
        row=4,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=chart_df.index,
            y=chart_df['MACD_SIGNAL'],
            mode='lines',
            name='MACD Signal',
            line=dict(color='#F59E0B', width=1.5),
        ),
        row=4,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=chart_df.index,
            y=chart_df['MACD_HIST'],
            name='MACD Hist',
            marker_color='#10B981',
            opacity=0.65,
        ),
        row=4,
        col=1,
    )

    fig.update_layout(
        height=820,
        showlegend=True,
        template='plotly_white',
        paper_bgcolor='white',
        plot_bgcolor='white',
        margin=dict(l=20, r=75, t=50, b=20),
        xaxis_rangeslider_visible=False,
        font=dict(color='#0F172A', family='Arial'),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='left',
            x=0,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor='rgba(148,163,184,0.35)',
            borderwidth=1,
            font=dict(color='#0F172A', size=10),
        ),
    )
    _overlay_plan(fig, plan)
    _overlay_custom_trade_labels(fig, chart_df, custom_entry, custom_stop, custom_exit)
    _overlay_current_price(fig, current_price)

    fig.update_yaxes(title_text='Price', row=1, col=1)
    fig.update_yaxes(title_text='Momentum', row=2, col=1)
    fig.update_yaxes(title_text='Volume', row=3, col=1)
    fig.update_yaxes(title_text='MACD', row=4, col=1)

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
            row=1,
            col=1,
        )


def _overlay_custom_trade_labels(
    fig: go.Figure,
    chart_df: pd.DataFrame,
    custom_entry: float | None,
    custom_stop: float | None,
    custom_exit: float | None,
) -> None:
    """Draw user-entered trade levels without crowding the chart with annotations."""
    if chart_df.empty:
        return
    for value, color, line_width in (
        (custom_entry, '#2563EB', 2.2),
        (custom_stop, '#DC2626', 2.4),
        (custom_exit, '#16A34A', 2.0),
    ):
        if value is None or pd.isna(value):
            continue
        fig.add_hline(
            y=float(value),
            line_dash='solid',
            line_color=color,
            line_width=line_width,
            row=1,
            col=1,
        )


def _overlay_current_price(fig: go.Figure, current_price: float) -> None:
    """Show the live price as a clean right-edge reference label."""
    fig.add_hline(
        y=current_price,
        line_dash='solid',
        line_color='#0F172A',
        line_width=2.0,
        row=1,
        col=1,
    )
    fig.add_annotation(
        x=1.02,
        y=current_price,
        xref='paper',
        yref='y',
        text=f'Current {money(current_price)}',
        showarrow=False,
        xanchor='left',
        yanchor='middle',
        font=dict(size=10, color='#0F172A', family='Arial', weight='bold'),
        bgcolor='rgba(255,255,255,0.96)',
        bordercolor='rgba(15,23,42,0.24)',
        borderwidth=1,
        borderpad=3,
        align='left',
    )


def _mini_metric_html(label: str, value: str, color: str) -> str:
    """Create a compact trading-dashboard metric tile with clean contrast."""
    return (
        f'<div style="display:inline-flex; align-items:center; justify-content:center; '
        f'flex-direction:column; min-width:88px; padding:4px 7px; border-radius:6px; '
        f'border:1px solid {color}; background:rgba(255,255,255,0.96); '
        f'box-shadow: inset 0 0 0 1px rgba(148,163,184,0.12); '
        f'color:{color}; font-family: Arial, sans-serif; '
        f'font-size:9px; font-weight:700; letter-spacing:0.08em; line-height:1.2; '
        f'text-transform:uppercase;">'
        f'<span style="font-size:7.2px; color:#475569; letter-spacing:0.14em;">{label}</span>'
        f'<span style="font-size:8.4px; color:#0F172A; letter-spacing:0.04em; margin-top:2px;">{value}</span>'
        f'</div>'
    )


def _render_trade_legend(
    plan_row: dict | None,
    current_price: float | None,
    custom_entry: float | None,
    custom_stop: float | None,
    custom_exit: float | None,
) -> None:
    """Display a compact color-coded legend above the chart instead of cluttered labels."""
    entries = []
    if current_price is not None:
        entries.append(('Current', current_price, '#0F172A'))
    for label, value, color in (
        (
            'Entry',
            custom_entry
            if custom_entry is not None and custom_entry > 0
            else plan_row.get('Entry')
            if plan_row
            else None,
            '#2563EB',
        ),
        (
            'Stop',
            custom_stop
            if custom_stop is not None and custom_stop > 0
            else plan_row.get('Stop')
            if plan_row
            else None,
            '#DC2626',
        ),
        (
            'Exit',
            custom_exit
            if custom_exit is not None and custom_exit > 0
            else plan_row.get('Target')
            if plan_row
            else None,
            '#16A34A',
        ),
    ):
        if value is None or pd.isna(value):
            continue
        entries.append((label, float(value), color))
    if not entries:
        return

    entry_value = None
    stop_value = None
    exit_value = None
    for label, value, _color in entries:
        if label == 'Entry':
            entry_value = float(value)
        elif label == 'Stop':
            stop_value = float(value)
        elif label == 'Exit':
            exit_value = float(value)

    setup_html = ''
    confidence_html = ''
    if plan_row:
        trend = float(plan_row.get('Trend Score', 0.0) or 0.0)
        support = max(0.0, min(1.0, float((plan_row.get('Dist 200D %', 0.0) or 0.0) * 0.1 + 0.5)))
        volume = max(0.0, min(1.0, float((plan_row.get('Rel Volume', 0.0) or 0.0) / 2.0)))
        rs = max(0.0, min(1.0, float((plan_row.get('RS Outperformance', 0.0) or 0.0) * 1.25 + 0.5)))
        risk_score = max(0.0, min(1.0, float((plan_row.get('R/R', 0.0) or 0.0) / 5.0)))
        accumulation_distribution = max(
            0.0,
            min(1.0, float((plan_row.get('Rel Volume', 0.0) or 0.0) * 0.6 + (trend * 0.4))),
        )
        verdict = EntryQualityScorer().score(
            trend_integrity=trend,
            support_quality=support,
            volume_absorption=volume,
            accumulation_distribution=accumulation_distribution,
            relative_strength=rs,
            risk_quality=risk_score,
        )
        quality_map = {
            'Strong dip': '#16A34A',
            'Neutral dip': '#F59E0B',
            'Weak dip': '#F97316',
            'Distribution trap': '#DC2626',
        }
        quality_color = quality_map.get(verdict.verdict, '#94A3B8')
        setup_html = _mini_metric_html('Setup', verdict.verdict, quality_color)
        confidence = plan_row.get('Confidence')
        if confidence is not None and not pd.isna(confidence):
            confidence_html = _mini_metric_html('Conf', str(int(float(confidence))), '#60A5FA')

    rr_html = ''
    if entry_value is not None and stop_value is not None and exit_value is not None:
        risk = abs(entry_value - stop_value)
        reward = abs(exit_value - entry_value)
        rr = reward / risk if risk else 0.0
        rr_html = _mini_metric_html('R:R', f'{rr:.1f}:1', '#94A3B8')

    html = '<div style="display:flex; flex-wrap:wrap; gap:5px; margin-bottom:8px; align-items:center;">'
    html += setup_html + confidence_html + rr_html
    for label, value, color in entries:
        html += _mini_metric_html(label, money(value), color)
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


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
    current_price = price
    to_entry = (
        (float(price) - float(row.get('Entry'))) / float(price)
        if price
        and row.get('Entry') is not None
        and not pd.isna(price)
        and not pd.isna(row.get('Entry'))
        else None
    )
    r1 = st.columns(4)
    r1[0].metric('Setup', dash(str(setup)) if setup is not None else dash(''))
    r1[1].metric('Confidence', dash(integer(row.get('Confidence'))))
    r1[2].metric('Current', dash(money(current_price)))
    r1[3].metric('Trend score', dash(score(row.get('Trend Score'))))
    r2 = st.columns(4)
    r2[0].metric('RS vs SPX', dash(percent(row.get('RS Outperformance'))))
    r2[1].metric('Rel volume', dash(multiple(row.get('Rel Volume'))))
    r2[2].metric('ATR %', dash(percent(atr_pct)))
    r2[3].metric('Market context', dash(str(row.get('Market Context') or '')))
    r3 = st.columns(4)
    r3[0].metric('Entry', dash(money(row.get('Entry'))), dash(percent(to_entry)), delta_color='off')
    r3[1].metric('Stop', dash(money(row.get('Stop'))), dash(percent(to_stop)), delta_color='off')
    r3[2].metric(
        'Target', dash(money(row.get('Target'))), dash(percent(to_target)), delta_color='off'
    )
    actionable = row.get('Actionable')
    if actionable is not None:
        r3[3].metric('Actionable', 'Yes' if bool(actionable) else 'No')
