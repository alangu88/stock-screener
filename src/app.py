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

st.set_page_config(page_title='S&P 500 Stock Screener', layout='wide')


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
    render_screener(cache, client, settings, engine, config)
    render_chart_section(client, settings, engine, view.rsi_period)


if __name__ == '__main__':
    run()
