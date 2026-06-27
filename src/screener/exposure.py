"""Pure look-through exposure analysis.

Combines direct single-stock holdings with the top-holdings of any funds held,
so concentration is measured on true economic exposure rather than ticker count.
Yahoo exposes only a fund's top ~10 holdings; the untracked remainder is
reported separately as a diversified tail rather than attributed to any name.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from src.data.yahoo_client import FundHoldings

# Curated symbol aliases: map a fund's local/home-market line, an alternate
# listing, or a secondary share class to the US-tradable symbol an investor
# would recognise, so the same company merges instead of splitting across
# direct + fund exposure.
SYMBOL_ALIASES: dict[str, str] = {
    '2330.TW': 'TSM',       # Taiwan Semiconductor
    'ASML.AS': 'ASML',      # ASML (local line vs the ADR funds also hold)
    '0700.HK': 'TCEHY',     # Tencent
    '9988.HK': 'BABA',      # Alibaba
    'HSBA.L': 'HSBC',       # HSBC
    'AZN.L': 'AZN',         # AstraZeneca
    'NOVN.SW': 'NVS',       # Novartis
    'ROG.SW': 'RHHBY',      # Roche
    'ROP.SW': 'RHHBY',      # Roche (alternate Yahoo code seen in VXUS)
    'GOOG': 'GOOGL',        # Alphabet Class C -> Class A (same company)
}


def normalize_symbol(symbol: str) -> str:
    """Resolve a cross-listed/ADR/dual-class symbol to its canonical ticker."""
    if not symbol:
        return symbol
    return SYMBOL_ALIASES.get(symbol.upper(), symbol)


@dataclass(frozen=True)
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
    name_lookup: dict[str, str] | None = None,
) -> tuple[list[EffectiveExposure], float]:
    """Resolve ``holdings`` into per-symbol effective exposure.

    Returns the exposures (sorted by total value, descending) and the dollar
    value of the untracked fund tail (the part of broad funds not covered by
    their top holdings). Cross-listed/ADR/dual-class symbols are normalised so
    the same company merges across direct holdings and fund top-holdings.

    ``name_lookup`` maps a (raw or canonical) ticker to a company name and is
    used to label direct holdings, which carry no name of their own.
    """
    name_lookup = name_lookup or {}
    direct: dict[str, float] = defaultdict(float)
    via_funds: dict[str, float] = defaultdict(float)
    names: dict[str, str] = {}
    tail_value = 0.0

    for ticker, value in holdings:
        if value is None or value <= 0:
            continue
        if ticker in fund_tickers:
            tail_value += _attribute_fund(fund_holdings.get(ticker), value, via_funds, names)
        else:
            canonical = normalize_symbol(ticker)
            direct[canonical] += value
            if label := (name_lookup.get(ticker) or name_lookup.get(canonical)):
                names.setdefault(canonical, label)

    return _build_exposures(direct, via_funds, names, account_value), tail_value


def _attribute_fund(
    fund: FundHoldings | None,
    value: float,
    via_funds: dict[str, float],
    names: dict[str, str],
) -> float:
    """Spread a fund position across its underlyings (mutating ``via_funds`` and
    ``names``) and return the untracked-tail dollar value.

    A fund with no published holdings is fully opaque, so its whole value is
    tail. Otherwise the portion not covered by the top holdings is tail.
    """
    if fund is None or not fund.holdings:
        return value
    covered = 0.0
    for symbol, weight in fund.holdings.items():
        canonical = normalize_symbol(symbol)
        via_funds[canonical] += value * weight
        covered += weight
        if symbol in fund.names:
            names.setdefault(canonical, fund.names[symbol])
    return value * max(0.0, 1.0 - covered)


def _build_exposures(
    direct: dict[str, float],
    via_funds: dict[str, float],
    names: dict[str, str],
    account_value: float,
) -> list[EffectiveExposure]:
    """Combine direct and via-fund dollars per symbol into sorted exposure rows."""
    exposures = []
    for symbol in direct.keys() | via_funds.keys():
        direct_value = direct.get(symbol, 0.0)
        fund_value = via_funds.get(symbol, 0.0)
        total_value = direct_value + fund_value
        exposures.append(
            EffectiveExposure(
                symbol=symbol,
                name=names.get(symbol, ''),
                direct_value=direct_value,
                fund_value=fund_value,
                total_value=total_value,
                weight=total_value / account_value if account_value > 0 else 0.0,
            )
        )
    exposures.sort(key=lambda exposure: exposure.total_value, reverse=True)
    return exposures
