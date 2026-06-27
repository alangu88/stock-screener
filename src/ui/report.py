"""Daily report section: render the latest headless markdown snapshot, if any."""

from __future__ import annotations

import streamlit as st

from src.ui.files import REPORT_FILE, read_file_text


def render_daily_report() -> None:
    """Show the latest headless daily report (reports/daily_report.md) if present."""
    with st.expander('Daily report', expanded=False):
        report = read_file_text(REPORT_FILE)
        if report.strip():
            st.markdown(report)
        else:
            st.info(
                'No daily report yet. Generate one with '
                '`python scripts/daily_report.py`.'
            )
