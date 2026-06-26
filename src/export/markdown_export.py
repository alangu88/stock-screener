"""Render a screener result frame as GitHub-flavoured Markdown.

Mirrors :mod:`src.export.csv_export`: a small, pure serialization layer so the
daily snapshot written to the README stays consistent with the rest of the
pipeline. No network, no Streamlit -- everything is derived from the result
DataFrame the engine already produces, which keeps it easy to unit test.
"""

from __future__ import annotations

import math

import pandas as pd

from src.screener.portfolio import sleeve_summary

START_MARKER = '<!-- SCREENER:START -->'
END_MARKER = '<!-- SCREENER:END -->'

# Columns shown in the README "top picks" table, in display order.
_PICK_COLUMNS = (
    'Ticker',
    'Setup',
    'Sleeve',
    'Entry',
    'Stop',
    'Target',
    'R/R',
    'Confidence',
    'Position Size %',
)

_SUMMARY_COLUMNS = (
    'Sleeve',
    'Positions',
    'Allocation %',
    'Portfolio Heat %',
    'Avg Confidence',
    'Avg R/R',
    'Avg Core Score',
)


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _money(value) -> str:
    return '-' if _is_missing(value) else f'{float(value):,.2f}'


def _ratio(value) -> str:
    return '-' if _is_missing(value) else f'{float(value):.2f}'


def _integer(value) -> str:
    return '-' if _is_missing(value) else f'{float(value):.0f}'


def _percent(value) -> str:
    return '-' if _is_missing(value) else f'{float(value) * 100:.2f}%'


def _text(value) -> str:
    return '' if _is_missing(value) else str(value)


_PICK_FORMATTERS = {
    'Ticker': _text,
    'Setup': _text,
    'Sleeve': _text,
    'Entry': _money,
    'Stop': _money,
    'Target': _money,
    'R/R': _ratio,
    'Confidence': _integer,
    'Position Size %': _percent,
}

_SUMMARY_FORMATTERS = {
    'Sleeve': _text,
    'Positions': _integer,
    'Allocation %': _percent,
    'Portfolio Heat %': _percent,
    'Avg Confidence': _integer,
    'Avg R/R': _ratio,
    'Avg Core Score': _ratio,
}


def _markdown_table(rows: list[list[str]], headers: list[str]) -> str:
    head = '| ' + ' | '.join(headers) + ' |'
    divider = '| ' + ' | '.join('---' for _ in headers) + ' |'
    body = ['| ' + ' | '.join(row) + ' |' for row in rows]
    return '\n'.join([head, divider, *body])


def results_to_markdown(df: pd.DataFrame, limit: int = 15) -> str:
    """Return a Markdown table of the top ``limit`` picks (by Rank Score)."""
    if df is None or df.empty:
        return '_No symbols matched the active filters._'

    ranked = df
    if 'Rank Score' in df.columns:
        ranked = df.sort_values(by='Rank Score', ascending=False)
    top = ranked.head(limit)

    columns = [c for c in _PICK_COLUMNS if c in top.columns]
    rows = [
        [_PICK_FORMATTERS[col](row.get(col)) for col in columns]
        for _, row in top.iterrows()
    ]
    return _markdown_table(rows, list(columns))


def sleeve_summary_to_markdown(df: pd.DataFrame) -> str:
    """Return a Markdown table of the Core/Satellite/Total sleeve roll-up."""
    if df is None or df.empty or 'Sleeve' not in df.columns:
        return '_No portfolio sleeves to summarize._'

    summary = sleeve_summary(df)
    columns = [c for c in _SUMMARY_COLUMNS if c in summary.columns]
    rows = [
        [_SUMMARY_FORMATTERS[col](row.get(col)) for col in columns]
        for _, row in summary.iterrows()
    ]
    return _markdown_table(rows, list(columns))


def build_snapshot_markdown(
    df: pd.DataFrame,
    *,
    generated_at: str,
    regime_label: str,
    symbols_screened: int,
    limit: int = 15,
) -> str:
    """Assemble the full README snapshot block (badges + tables + disclaimer)."""
    matches = 0 if df is None else len(df)
    badges = ' '.join(
        (
            f'![Matches](https://img.shields.io/badge/matches-{matches}-blue)',
            f'![Regime](https://img.shields.io/badge/regime-{_badge_value(regime_label)}-informational)',
            f'![Screened](https://img.shields.io/badge/screened-{symbols_screened}-lightgrey)',
        )
    )
    return '\n\n'.join(
        (
            badges,
            f'_Last updated: {generated_at}_',
            '#### Top picks',
            results_to_markdown(df, limit=limit),
            '#### Portfolio sleeves (Core / Satellite)',
            sleeve_summary_to_markdown(df),
            '> Mechanical signals for research only \u2014 not trade recommendations.',
        )
    )


def build_unavailable_markdown(*, generated_at: str, reason: str = '') -> str:
    """Fallback block when the data feed is unavailable, so the README stays valid."""
    detail = f' ({reason})' if reason else ''
    return '\n\n'.join(
        (
            f'_Snapshot data temporarily unavailable{detail}._',
            f'_Last attempted: {generated_at}_',
        )
    )


def inject_between_markers(
    text: str,
    block: str,
    start_marker: str = START_MARKER,
    end_marker: str = END_MARKER,
) -> str:
    """Replace the region between the markers in ``text`` with ``block``.

    The markers themselves are preserved. Raises ``ValueError`` if either marker
    is missing or out of order so a malformed README fails loudly instead of
    silently dropping content.
    """
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start == -1 or end == -1 or end < start:
        raise ValueError('README markers not found or out of order.')
    before = text[: start + len(start_marker)]
    after = text[end:]
    return f'{before}\n{block}\n{after}'


def _badge_value(value: str) -> str:
    """Sanitize a label for use inside a shields.io badge path segment."""
    cleaned = str(value).strip() or 'unknown'
    return cleaned.replace('-', '--').replace(' ', '_')
