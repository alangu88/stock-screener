"""Filesystem paths and read/write helpers for the user's data files.

The app uses a two-file privacy model: committed composition (``portfolio.txt`` /
``watchlist.txt``) plus a git-ignored ``positions.txt`` holding private sizes.
These helpers centralize the paths and the parsing/append logic so the render
modules stay focused on layout.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.data.yahoo_client import YahooFinanceClient
from src.screener.holdings import parse_portfolio

_ROOT = Path(__file__).resolve().parents[2]

# Persistent, private list of the user's positions. Git-ignored so real
# holdings never get committed; auto-loaded into the app on every start.
POSITIONS_FILE = _ROOT / 'positions.txt'

# Committed companions: portfolio composition (tickers + sleeve, no sizes) and
# the watchlist of names we follow but do not (yet) hold.
PORTFOLIO_FILE = _ROOT / 'portfolio.txt'
WATCHLIST_FILE = _ROOT / 'watchlist.txt'

# Git-ignored markdown snapshot written by scripts/daily_report.py.
REPORT_FILE = _ROOT / 'reports' / 'daily_report.md'

_POSITIONS_PLACEHOLDER = (
    '# One ticker per line. Optionally add entry price and shares.\n'
    '# Format: TICKER, entry_price, shares   (price and shares optional)\n'
    '# Group positions by account with a [Section] header.\n'
    '# Repeat a ticker per lot to average the cost basis.\n'
    '#\n'
    '# [Taxable]\n'
    '# AAPL, 150, 10\n'
    '# AAPL, 170, 20\n'
    '# MSFT, 410.50\n'
    '#\n'
    '# [Roth IRA]\n'
    '# NVDA, 95.20, 100\n'
)


def read_file_text(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''


def initial_positions_text() -> str:
    if POSITIONS_FILE.exists():
        return POSITIONS_FILE.read_text(encoding='utf-8')
    return _POSITIONS_PLACEHOLDER


def reload_positions_input() -> None:
    """Refresh the positions editor from disk (runs before widget re-instantiation)."""
    st.session_state['positions_input'] = initial_positions_text()


def positions_sections() -> list[str]:
    """Account section names (``[Section]`` headers) present in positions.txt."""
    sections = []
    for line in read_file_text(POSITIONS_FILE).splitlines():
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            name = stripped[1:-1].strip()
            if name and name not in sections:
                sections.append(name)
    return sections


def insert_position_line(text: str, section: str | None, line: str) -> str:
    """Return ``text`` with ``line`` inserted under ``section`` (or appended)."""
    if not section:
        if not text.strip():
            return f'{line}\n'
        sep = '' if text.endswith('\n') else '\n'
        return f'{text}{sep}{line}\n'
    target = f'[{section}]'
    out: list[str] = []
    inserted = False
    for existing in text.splitlines():
        out.append(existing)
        if not inserted and existing.strip() == target:
            out.append(line)
            inserted = True
    if not inserted:
        if out and out[-1].strip():
            out.append('')
        out.extend([target, line])
    return '\n'.join(out) + '\n'


def append_to_positions(section: str | None, ticker: str, entry: float | None, shares: float) -> None:
    """Append ``TICKER, cost_basis, shares`` to positions.txt under ``section``."""
    parts = [ticker]
    if entry and not pd.isna(entry):
        parts.append(f'{float(entry):.2f}')
    else:
        parts.append('')
    parts.append(f'{float(shares):g}')
    line = ', '.join(parts)
    new_text = insert_position_line(read_file_text(POSITIONS_FILE), section, line)
    POSITIONS_FILE.write_text(new_text, encoding='utf-8')


def watchlist_tickers() -> list[str]:
    """Tickers from the committed watchlist (sleeve tags, if any, ignored)."""
    entries = parse_portfolio(read_file_text(WATCHLIST_FILE))
    return [entry.ticker for entry in entries]


def etf_tickers(client: YahooFinanceClient, tickers: list[str]) -> set[str]:
    """Return the subset of ``tickers`` Yahoo classifies as funds (ETF/MUTUALFUND).

    Used to exclude funds from the individual-stock diversification cap. Unknown
    quote types fall back to treating the name as a stock (not in the set).
    """
    if not tickers:
        return set()
    fundamentals = client.fetch_fundamentals(tickers)
    funds = {'ETF', 'MUTUALFUND'}
    return {
        t for t, f in fundamentals.items()
        if (f.quote_type or '').upper() in funds
    }
