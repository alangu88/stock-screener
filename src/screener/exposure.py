"""Pure look-through exposure analysis.

Combines direct single-stock holdings with the top-holdings of any funds held,
so concentration is measured on true economic exposure rather than ticker count.
Yahoo exposes only a fund's top ~10 holdings; the untracked remainder is
reported separately as a diversified tail rather than attributed to any name.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.data.yahoo_client import FundHoldings

# Curated cross-listing aliases: map a fund's local/home-market line (or an
# alternate listing) to the US-tradable symbol an investor would recognise, so
# the same company merges instead of splitting across direct + fund exposure.
ADR_ALIASES: dict[str, str] = {
    '2330.TW': 'TSM',       # Taiwan Semiconductor
    'ASML.AS': 'ASML',      # ASML (local line vs the ADR funds also hold)
    '0700.HK': 'TCEHY',     # Tencent
    '9988.HK': 'BABA',      # Alibaba
    'HSBA.L': 'HSBC',       # HSBC
    'AZN.L': 'AZN',         # AstraZeneca
    'NOVN.SW': 'NVS',       # Novartis
    'ROG.SW': 'RHHBY',      # Roche
    'ROP.SW': 'RHHBY',      # Roche (alternate Yahoo code seen in VXUS)
}


def normalize_symbol(symbol: str) -> str:
    """Resolve a cross-listed/ADR symbol to its canonical US-tradable ticker."""
    if not symbol:
        return symbol
    return ADR_ALIASES.get(symbol.upper(), symbol)


@dataclass
class EffectiveExposure:
    """Combined direct + via-fund exposure to a single underlying symbol."""

    symbol: str
    name: str
    direct_value: float
    fund_value: float
    total_value: float
    weight: float


def look_through_exposure(
    holdings: list[tuple[str, float]],
    fund_holdings: dict[str, FundHoldings],
    fund_tickers: set[str],
    account_value: float,
) -> tuple[list[EffectiveExposure], float]:
    """Resolve ``holdings`` into per-symbol effective exposure.

    Returns the exposures (sorted by total value, descending) and the dollar
    value of the untracked fund tail (the part of broad funds not covered by
    their top holdings). Cross-listed/ADR symbols are normalised so the same
    company merges across direct holdings and fund top-holdings.
    """
    direct: dict[str, float] = {}
    via_funds: dict[str, float] = {}
    names: dict[str, str] = {}
    tail_value = 0.0

    for ticker, value in holdings:
        if value is None or value <= 0:
            continue
        if ticker in fund_tickers and ticker in fund_holdings:
            fund = fund_holdings[ticker]
            covered = 0.0
            for symbol, weight in fund.holdings.items():
                canonical = normalize_symbol(symbol)
                via_funds[canonical] = via_funds.get(canonical, 0.0) + value * weight
                covered += weight
                if canonical not in names and symbol in fund.names:
                    names[canonical] = fund.names[symbol]
            tail_value += value * max(0.0, 1.0 - covered)
        elif ticker in fund_tickers:
            # Fund with no look-through data: treat the whole sleeve as opaque.
            tail_value += value
        else:
            canonical = normalize_symbol(ticker)
            direct[canonical] = direct.get(canonical, 0.0) + value

    exposures: list[EffectiveExposure] = []
    for symbol in set(direct) | set(via_funds):
        direct_value = direct.get(symbol, 0.0)
        fund_value = via_funds.get(symbol, 0.0)
        total = direct_value + fund_value
        weight = total / account_value if account_value > 0 else 0.0
        exposures.append(
            EffectiveExposure(symbol, names.get(symbol, ''), direct_value, fund_value, total, weight)
        )

    exposures.sort(key=lambda exposure: exposure.total_value, reverse=True)
    return exposures, tail_value


def theme_rollup(
    exposures: list[EffectiveExposure],
    tail_value: float,
    industry_map: dict[str, str],
    account_value: float,
) -> list[tuple[str, float, float]]:
    """Group effective exposure by industry/theme.

    Returns ``(label, value, weight)`` tuples sorted by value descending. The
    untracked fund tail is bucketed as ``Other / diversified``.
    """
    buckets: dict[str, float] = {}
    for exposure in exposures:
        label = industry_map.get(exposure.symbol) or 'Unknown'
        buckets[label] = buckets.get(label, 0.0) + exposure.total_value
    if tail_value > 0:
        buckets['Other / diversified'] = buckets.get('Other / diversified', 0.0) + tail_value

    rows = [
        (label, value, value / account_value if account_value > 0 else 0.0)
        for label, value in buckets.items()
    ]
    rows.sort(key=lambda row: row[1], reverse=True)
    return rows
