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
from src.ui.positions import render_positions  # noqa: E402
from src.ui.recommendations import render_recommendations  # noqa: E402
from src.ui.report import render_daily_report  # noqa: E402
from src.ui.services import get_services  # noqa: E402
from src.ui.sidebar import render_cache_controls, render_sidebar  # noqa: E402

st.set_page_config(page_title='Position Manager & Screener', layout='wide')


def run() -> None:
    settings, cache, client, engine = get_services()

    st.title('Position Manager & S&P 500 Screener')
    st.caption(
        'Track your holdings, size adds by risk, surface high-conviction setups, '
        'and chart any name — powered by Yahoo Finance data with daily caching.'
    )

    render_cache_controls(cache)
    config, portfolio, view = render_sidebar(settings)
    engine.portfolio = portfolio
    render_positions(client, settings, engine, config)
    render_recommendations(cache, client, settings, engine)
    render_chart_section(client, settings, engine, view.rsi_period)
    render_daily_report()


if __name__ == '__main__':
    run()
