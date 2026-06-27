"""Render screener result frames as GitHub-flavoured Markdown.

Mirrors :mod:`src.export.csv_export`: a small, pure serialization layer so the
daily snapshot written to the README stays consistent with the rest of the
pipeline. No network, no Streamlit -- everything is derived from the frames the
engine already produces, which keeps it easy to unit test.

The snapshot has two sections: the **watchlist** (your holdings plus followed
names, monitored whether or not they are actionable) and the **recommended
adds** (fresh high-conviction setups that clear the advisor gates).
"""

from __future__ import annotations

import math

import pandas as pd

from src.config import Settings

START_MARKER = '<!-- SCREENER:START -->'
END_MARKER = '<!-- SCREENER:END -->'

# Columns shown in the "recommended adds" table, in display order.
_PICK_COLUMNS = (
    'Ticker',
    'Setup',
    'Sleeve',
    'Entry',
    'Stop',
    'Target',
    'R/R',
    'Confidence',
    'Rank Score',
    'Position Size %',
)

# Columns shown in the "watchlist" monitor table, in display order.
_WATCHLIST_COLUMNS = (
    'Ticker',
    'Setup',
    'Confidence',
    'R/R',
    'Entry',
    'Stop',
    'Target',
    'Rank Score',
    'Actionable',
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


def _flag(value) -> str:
    return 'Yes' if not _is_missing(value) and bool(value) else 'No'


_PICK_FORMATTERS = {
    'Ticker': _text,
    'Setup': _text,
    'Sleeve': _text,
    'Entry': _money,
    'Stop': _money,
    'Target': _money,
    'R/R': _ratio,
    'Confidence': _integer,
    'Rank Score': _ratio,
    'Position Size %': _percent,
}

_WATCHLIST_FORMATTERS = {
    'Ticker': _text,
    'Setup': _text,
    'Confidence': _integer,
    'R/R': _ratio,
    'Entry': _money,
    'Stop': _money,
    'Target': _money,
    'Rank Score': _ratio,
    'Actionable': _flag,
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


def watchlist_to_markdown(df: pd.DataFrame, limit: int = 50) -> str:
    """Markdown table of the watchlist (held + followed names), strongest first.

    Every watchlist name is shown regardless of gating; the ``Actionable``
    column flags those currently clearing the screen gates.
    """
    if df is None or df.empty:
        return '_Watchlist is empty._'

    ranked = df
    if 'Rank Score' in df.columns:
        ranked = df.sort_values(by='Rank Score', ascending=False)
    top = ranked.head(limit)

    columns = [c for c in _WATCHLIST_COLUMNS if c in top.columns]
    rows = [
        [_WATCHLIST_FORMATTERS[col](row.get(col)) for col in columns]
        for _, row in top.iterrows()
    ]
    return _markdown_table(rows, list(columns))


def recommended_to_markdown(df: pd.DataFrame, limit: int = 15) -> str:
    """Markdown table of fresh high-conviction adds (already gated upstream)."""
    if df is None or df.empty:
        return '_No candidates cleared the recommendation gates — sitting tight._'
    return results_to_markdown(df, limit=limit)


def _parameters_line(settings: Settings) -> str:
    """One-line summary of the active risk and portfolio parameters."""
    parts = (
        f'Risk/trade {settings.risk_per_trade:.0%}',
        f'Core band {settings.core_allocation_min:.0%}\u2013{settings.core_allocation_max:.0%}',
        f'Add gates conf \u2265 {settings.rec_min_confidence:.0f} & R/R \u2265 '
        f'{settings.rec_min_reward_risk:.1f}',
        f'Max {settings.max_individual_stocks} single-stock names',
        f'Max position {settings.max_position_weight:.0%}',
    )
    return '> **Parameters:** ' + ' \u00b7 '.join(parts)


def build_snapshot_markdown(
    watchlist_df: pd.DataFrame,
    recommended_df: pd.DataFrame,
    *,
    settings: Settings,
    generated_at: str,
    regime_label: str,
    watchlist_count: int,
    limit: int = 15,
) -> str:
    """Assemble the README snapshot: watchlist monitor + recommended adds."""
    adds = 0 if recommended_df is None else len(recommended_df)
    badges = ' '.join(
        (
            f'![Regime](https://img.shields.io/badge/regime-{_badge_value(regime_label)}-informational)',
            f'![Watchlist](https://img.shields.io/badge/watchlist-{watchlist_count}-blue)',
            f'![Adds](https://img.shields.io/badge/adds-{adds}-success)',
        )
    )
    return '\n\n'.join(
        (
            badges,
            f'_Last updated: {generated_at}_',
            _parameters_line(settings),
            '#### Watchlist (your holdings + followed names)',
            watchlist_to_markdown(watchlist_df),
            '#### Recommended adds (clear the gates)',
            recommended_to_markdown(recommended_df, limit=limit),
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
