"""Canonical schema for the screener result table.

Defining the column order in one place keeps the engine output, CSV export,
and UI from drifting apart. Presentation concerns (number formatting) live in
the UI layer; this module only describes *what* a result row contains.
"""

from __future__ import annotations

# Ordered result columns. The engine emits exactly these, the CSV export uses
# this order, and the UI sorts/formats against these names.
RESULT_COLUMNS: tuple[str, ...] = (
    'Ticker',
    'Company Name',
    'Setup',
    'Confidence',
    'Rank Score',
    'Entry',
    'Stop',
    'Target',
    'Risk %',
    'Reward %',
    'R/R',
    'Reason',
    'Key Factors',
    'Risks',
    'Trend Score',
    'RS Outperformance',
    'Rel Volume',
    'Beta',
    'Return 3M',
    'ATR %',
    'Dist 200D %',
    'Dollar ADV',
    'Div Yield',
    'Sector',
    'Market Cap',
    'PE Ratio',
    'Revenue Growth',
    'Price',
    'Market Context',
)
