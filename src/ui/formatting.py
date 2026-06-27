"""Display formatters shared across the UI panels.

Each formatter turns a raw numeric/text value into a display string and tolerates
``None``/NaN by returning an empty string, so they can be mapped over dataframe
columns without guarding every cell.
"""

from __future__ import annotations

import math

import pandas as pd

EMDASH = '\u2014'


def fmt(value, spec: str = '.2f', scale: float = 1.0, suffix: str = '') -> str:
    """Format a finite number with ``spec``; blank for missing/non-finite input."""
    if pd.isna(value) or not math.isfinite(float(value)):
        return ''
    return f'{float(value) * scale:{spec}}{suffix}'


def money(value) -> str:
    return fmt(value, '.2f')


def percent(value) -> str:
    return fmt(value, '.2f', 100, '%')


def score(value) -> str:
    return fmt(value, '.2f')


def integer(value) -> str:
    return fmt(value, '.0f')


def shares(value) -> str:
    """Share counts to the thousandth (brokers support fractional shares)."""
    return fmt(value, '.3f')


def multiple(value) -> str:
    return fmt(value, '.2f', 1.0, 'x')


def dash(text: str) -> str:
    """Return ``text`` or an em dash placeholder when it is empty/falsey."""
    return text if text else EMDASH


def apply_formatters(df: pd.DataFrame, formatters: dict) -> pd.DataFrame:
    """Format the columns named in ``formatters``; leave the rest untouched."""
    out = df.copy()
    for column, formatter in formatters.items():
        if column in out.columns:
            out[column] = out[column].map(formatter)
    return out
