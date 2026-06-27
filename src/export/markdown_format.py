"""Shared Markdown formatting primitives.

Both the README snapshot (:mod:`src.export.markdown_export`) and the local daily
report (``scripts/daily_report.py``) render numbers and tables into
GitHub-flavoured Markdown. The surfaces differ only in their "missing value"
placeholder and currency prefix, so the actual formatting logic lives here and
each caller supplies its own conventions.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def is_missing(value: object) -> bool:
    """Return ``True`` for ``None`` or NaN floats."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def number(
    value: object,
    spec: str = '.2f',
    *,
    scale: float = 1.0,
    prefix: str = '',
    suffix: str = '',
    missing: str = '\u2014',
) -> str:
    """Format ``value`` with ``spec``, or return ``missing`` when absent."""
    if is_missing(value):
        return missing
    return f'{prefix}{float(value) * scale:{spec}}{suffix}'


def text(value: object, *, missing: str = '\u2014') -> str:
    """Stringify ``value``, returning ``missing`` for empty/absent input."""
    return missing if value is None or value == '' else str(value)


def table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    empty: str = '_None._',
) -> str:
    """Render a Markdown table, or ``empty`` when there are no rows."""
    if not rows:
        return empty
    head = '| ' + ' | '.join(headers) + ' |'
    divider = '| ' + ' | '.join(['---'] * len(headers)) + ' |'
    body = ['| ' + ' | '.join(row) + ' |' for row in rows]
    return '\n'.join([head, divider, *body])
