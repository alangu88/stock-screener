"""Filesystem helper for the screener's watchlist (committed, no positions)."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# The watchlist of names to screen alongside the S&P 500. One ticker per line,
# ``#`` comments; safe to commit (no sizes or cost basis).
WATCHLIST_FILE = _ROOT / 'watchlist.txt'


def watchlist_tickers() -> list[str]:
    """Read plain ticker symbols (one per line, ``#`` comments) from the watchlist."""
    if not WATCHLIST_FILE.exists():
        return []
    out: list[str] = []
    for raw in WATCHLIST_FILE.read_text(encoding='utf-8').splitlines():
        line = raw.split('#', 1)[0].strip()
        if line:
            out.append(line.upper())
    return out
