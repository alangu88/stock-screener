"""Streamlit entrypoint: wires the UI sections into a single page.

Run with ``streamlit run src/app.py``. The actual rendering lives in the
``src/ui`` package; this module only composes the sections in order.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ``streamlit run src/app.py`` puts the script's own folder (``src/``) on
# sys.path, not the repository root, so the absolute ``src.*`` imports below
# would fail. Add the repo root explicitly to make them resolve regardless of
# how or from where the app is launched.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from src.ui.charts import render_chart_section  # noqa: E402
from src.ui.screener import render_screener  # noqa: E402
from src.ui.services import get_services  # noqa: E402
from src.ui.sidebar import render_cache_controls, render_sidebar  # noqa: E402

st.set_page_config(
    page_title='S&P 500 Stock Screener',
    layout='wide',
    initial_sidebar_state='expanded',
)

st.markdown(
    """
    <style>
        .stApp {
            background: #f8fafc;
            color: #0f172a;
        }
        .stApp * {
            color: #0f172a;
        }
        .stTabs [data-baseweb="tab-list"] {
            background: #ffffff;
            border-radius: 8px;
            padding: 6px;
            border: 1px solid rgba(148, 163, 184, 0.35);
        }
        .stTabs [data-baseweb="tab"] {
            color: #334155;
            font-weight: 600;
        }
        .stTabs [aria-selected="true"] {
            background: #e2e8f0;
            color: #0f172a;
            border-radius: 6px;
        }
        .stDataFrame, .stDataFrame > div {
            background: #ffffff;
        }
        div[data-testid="stMetricValue"] {
            color: #0f172a !important;
        }
        div[data-testid="stMetricLabel"] {
            color: #475569 !important;
        }
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
        }
        .stButton > button {
            background: #ffffff;
            color: #0f172a;
            border: 1px solid rgba(148, 163, 184, 0.75);
            border-radius: 8px;
            font-weight: 700;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
        }
        .stButton > button:hover {
            border-color: rgba(59, 130, 246, 0.8);
            box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.2);
        }
        .screen-status-panel {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 12px;
            margin-bottom: 10px;
            border: 1px solid rgba(148, 163, 184, 0.9);
            border-radius: 8px;
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
            box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.02);
        }
        .screen-status-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 54px;
            padding: 4px 8px;
            border-radius: 999px;
            background: #e2e8f0;
            color: #0f172a;
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 0.14em;
            text-transform: uppercase;
        }
        .screen-status-text {
            color: #0f172a;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        div[data-testid="stProgressBar"] > div {
            background: linear-gradient(90deg, #2563eb 0%, #60a5fa 100%);
            border-radius: 999px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def run() -> None:
    settings, cache, client, engine = get_services()

    st.title('S&P 500 Stock Screener')
    st.caption(
        'Data-driven screening for high-conviction technical setups — ranked by '
        'quality and market context, with structural entry/stop/target levels and '
        'charts for any name. Powered by Yahoo Finance data with daily caching.'
    )

    render_cache_controls(cache)
    config, view = render_sidebar(settings)
    render_screener(cache, client, settings, engine, config, view)
    render_chart_section(client, settings, engine, view.rsi_period)


if __name__ == '__main__':
    run()
