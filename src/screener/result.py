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
    'Sleeve',
    'Confidence',
    'Core Score',
    'Rank Score',
    'Position Size %',
    'Entry',
    'Stop',
    'Target',
    'Risk %',
    'Risk Contribution %',
    'Reward %',
    'R/R',
    'Reason',
    'Key Factors',
    'Risks',
    'Trend Score',
    'RS Outperformance',
    'Rel Volume',
    'Market Cap',
    'PE Ratio',
    'Revenue Growth',
    'Price',
    'Market Context',
)

# Columns offered in the "Sort By" menu, in display order.
SORTABLE_COLUMNS: tuple[str, ...] = (
    'Rank Score',
    'Core Score',
    'Position Size %',
    'Confidence',
    'Setup',
    'Sleeve',
    'R/R',
    'Reward %',
    'Risk %',
    'Entry',
    'Stop',
    'Target',
    'Ticker',
    'Company Name',
    'Trend Score',
    'RS Outperformance',
    'Rel Volume',
    'Market Cap',
    'PE Ratio',
    'Revenue Growth',
    'Price',
)
