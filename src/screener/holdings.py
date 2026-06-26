"""Positions and holdings monitoring.

A lightweight complement to the setup screener: instead of hunting the whole
S&P 500 for new setups, this tracks a *user-supplied* list of tickers (your
owned positions and/or names you follow) against the 20 / 50 / 200 moving
averages, and -- when entry price and share count are supplied -- reports
unrealized P&L, position value, and portfolio weight.

All functions here are pure: parsing is string-only and ``build_monitor`` takes
already-fetched history, so the logic is fully unit-testable without network.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.analysis.indicators import ema, sma
from src.config import Settings
from src.data.universe import normalize_ticker

# Number of recent bars over which a 50/200 crossover still counts as "recent".
CROSS_LOOKBACK = 10

# How many of the largest positions to roll up for the top-N concentration stat.
TOP_N_CONCENTRATION = 5

# Herfindahl-Hirschman Index bands (sum of squared weights, 0..1) that classify
# how concentrated a book is. Mirrors the antitrust convention (0.15 / 0.25)
# applied to portfolio weights.
HHI_DIVERSIFIED = 0.15
HHI_MODERATE = 0.25

# Bucket label for positions listed before (or without) any ``[Account]`` header.
DEFAULT_ACCOUNT = 'Unassigned'

MONITOR_COLUMNS = (
    'Ticker',
    'Account',
    'Price',
    'EMA20',
    'SMA50',
    'SMA200',
    '% vs EMA20',
    '% vs SMA50',
    '% vs SMA200',
    'Trend',
    'Signal',
    '50/200 Cross',
    'Entry',
    'Unreal P&L %',
    'Shares',
    'Value',
    'Weight %',
    'Unreal P&L $',
)


@dataclass(frozen=True)
class PositionEntry:
    ticker: str
    entry_price: float | None = None
    shares: float | None = None
    account: str | None = None


@dataclass(frozen=True)
class ConcentrationStats:
    positions: int           # number of sized holdings
    total_value: float       # total market value of those holdings
    largest_ticker: str
    largest_weight: float    # weight of the single biggest position (0..1)
    top_n_weight: float      # combined weight of the TOP_N_CONCENTRATION largest
    hhi: float               # Herfindahl-Hirschman Index, sum of squared weights
    effective_positions: float  # 1 / HHI: equal-weight-equivalent holding count
    label: str               # 'Diversified' / 'Moderately concentrated' / 'Concentrated'



def parse_positions(text: str) -> list[PositionEntry]:
    """Parse a free-form list of positions into entries.

    One ticker per line; optional ``entry_price`` and ``shares`` follow,
    separated by commas, whitespace, or tabs. ``#`` starts a comment. A line of
    the form ``[Account Name]`` opens a section: every entry below it belongs to
    that account until the next header. Example::

        [Taxable]
        AAPL
        MSFT, 410.50

        [Roth IRA]
        NVDA, 95.20, 100     # ticker, entry price, shares

    Listing the same ticker more than once within an account merges the lines
    into a single position: the shares are summed and the entry price becomes
    the share-weighted **average cost basis** across the priced lots. Example::

        [Taxable]
        AAPL, 150, 10        # first buy
        AAPL, 170, 20        # added later -> 30 sh @ 163.33 avg cost

    Repeated tickers with no share counts keep the first line (watch-only). The
    same ticker may appear under different accounts and stays separate.
    Unparseable numbers are treated as missing rather than raising.
    """
    lots: list[tuple[str | None, str, float | None, float | None]] = []
    current_account: str | None = None
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('[') and line.endswith(']'):
            current_account = line[1:-1].strip() or None
            continue
        parts = [p for p in line.replace(',', ' ').replace('\t', ' ').split() if p]
        symbol = normalize_ticker(parts[0])
        if not symbol:
            continue
        entry_price = _to_float(parts[1]) if len(parts) > 1 else None
        shares = _to_float(parts[2]) if len(parts) > 2 else None
        lots.append((current_account, symbol, entry_price, shares))
    return _aggregate_lots(lots)


def _aggregate_lots(
    lots: list[tuple[str | None, str, float | None, float | None]],
) -> list[PositionEntry]:
    """Merge lots that share an ``(account, ticker)`` into one position."""
    order: list[tuple[str | None, str]] = []
    grouped: dict[tuple[str | None, str], list[tuple[float | None, float | None]]] = {}
    for account, symbol, price, shares in lots:
        key = (account, symbol)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append((price, shares))

    entries: list[PositionEntry] = []
    for account, symbol in order:
        price, shares = _combine_lots(grouped[(account, symbol)])
        entries.append(PositionEntry(symbol, price, shares, account))
    return entries


def _combine_lots(
    lots: list[tuple[float | None, float | None]],
) -> tuple[float | None, float | None]:
    """Collapse multiple lots into ``(avg_cost, total_shares)``.

    Only lots that specify a share count contribute to the position; the average
    cost is weighted by the shares of the priced lots. With no share counts at
    all the first line wins, matching plain watch-only de-duplication.
    """
    if len(lots) == 1:
        return lots[0]
    with_shares = [(p, s) for p, s in lots if s is not None]
    if not with_shares:
        return lots[0]
    total_shares = sum(s for _, s in with_shares)
    priced = [(p, s) for p, s in with_shares if p is not None]
    weight = sum(s for _, s in priced)
    if priced and weight > 0:
        avg_cost = sum(p * s for p, s in priced) / weight
    else:
        avg_cost = next((p for p, _ in lots if p is not None), None)
    return avg_cost, total_shares



def build_monitor(
    entries: list[PositionEntry],
    history: dict[str, pd.DataFrame],
    settings: Settings,
) -> pd.DataFrame:
    """Build the moving-average monitor table for ``entries``.

    ``history`` maps ticker -> OHLCV frame (as returned by the Yahoo client).
    Tickers with no usable history are still listed, with blank metrics.
    """
    rows = [_monitor_row(entry, history.get(entry.ticker), settings) for entry in entries]
    df = pd.DataFrame(rows, columns=list(MONITOR_COLUMNS))
    _add_portfolio_weight(df)
    return df


def _monitor_row(
    entry: PositionEntry, df: pd.DataFrame | None, settings: Settings
) -> dict:
    row: dict = {col: None for col in MONITOR_COLUMNS}
    row['Ticker'] = entry.ticker
    row['Account'] = entry.account
    row['Entry'] = entry.entry_price
    row['Shares'] = entry.shares

    close = _close_series(df)
    if close is None or close.empty:
        row['Signal'] = 'No data'
        return row

    price = float(close.iloc[-1])
    ema20 = _last(ema(close, settings.ema_window))
    sma50 = _last(sma(close, settings.sma_short_window))
    sma200 = _last(sma(close, settings.sma_long_window))

    row['Price'] = price
    row['EMA20'] = ema20
    row['SMA50'] = sma50
    row['SMA200'] = sma200
    row['% vs EMA20'] = _pct_diff(price, ema20)
    row['% vs SMA50'] = _pct_diff(price, sma50)
    row['% vs SMA200'] = _pct_diff(price, sma200)
    row['Trend'] = _trend_label(price, ema20, sma50, sma200)
    row['Signal'] = _signal(price, sma50, sma200)
    row['50/200 Cross'] = _cross_state(close, settings)

    if entry.entry_price:
        row['Unreal P&L %'] = price / entry.entry_price - 1.0
    if entry.shares is not None:
        row['Value'] = price * entry.shares
        if entry.entry_price:
            row['Unreal P&L $'] = (price - entry.entry_price) * entry.shares
    return row


def _add_portfolio_weight(df: pd.DataFrame) -> None:
    total_value = df['Value'].dropna().sum()
    if total_value > 0:
        df['Weight %'] = df['Value'].apply(
            lambda v: v / total_value if pd.notna(v) else None
        )


def has_accounts(monitor: pd.DataFrame) -> bool:
    """True when at least one position was tagged with an ``[Account]`` section."""
    return 'Account' in monitor.columns and bool(monitor['Account'].notna().any())


def account_groups(monitor: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    """Split the monitor into ``(account, rows)`` groups in first-seen order.

    Positions with no account are bucketed under :data:`DEFAULT_ACCOUNT`.
    """
    labels = monitor['Account'].fillna(DEFAULT_ACCOUNT)
    return [(label, monitor[labels == label]) for label in labels.drop_duplicates()]


def concentration_summary(monitor: pd.DataFrame) -> ConcentrationStats | None:
    """Summarize how concentrated the *sized* holdings are.

    Only rows with a positive ``Value`` (i.e. you entered shares) count toward
    the portfolio; watch-only tickers are ignored. Returns ``None`` when there
    are no sized positions to analyze.
    """
    held = monitor.loc[monitor['Value'].notna(), ['Ticker', 'Value']].copy()
    held = held[held['Value'] > 0]
    if held.empty:
        return None

    total_value = float(held['Value'].sum())
    weights = (held['Value'] / total_value).sort_values(ascending=False)

    hhi = float((weights ** 2).sum())
    largest_weight = float(weights.iloc[0])
    largest_ticker = str(held.loc[weights.index[0], 'Ticker'])
    top_n_weight = float(weights.head(TOP_N_CONCENTRATION).sum())

    return ConcentrationStats(
        positions=int(len(weights)),
        total_value=total_value,
        largest_ticker=largest_ticker,
        largest_weight=largest_weight,
        top_n_weight=top_n_weight,
        hhi=hhi,
        effective_positions=1.0 / hhi,
        label=_concentration_label(hhi),
    )


def _concentration_label(hhi: float) -> str:
    if hhi < HHI_DIVERSIFIED:
        return 'Diversified'
    if hhi < HHI_MODERATE:
        return 'Moderately concentrated'
    return 'Concentrated'


def _close_series(df: pd.DataFrame | None) -> pd.Series | None:
    if df is None or df.empty or 'Close' not in df.columns:
        return None
    return df['Close'].dropna()


def _trend_label(price: float, ema20: float | None, sma50: float | None, sma200: float | None) -> str:
    if None in (ema20, sma50, sma200):
        return 'Insufficient history'
    if price > ema20 > sma50 > sma200:
        return 'Uptrend (stacked)'
    if price < ema20 < sma50 < sma200:
        return 'Downtrend (stacked)'
    return 'Mixed'


def _signal(price: float, sma50: float | None, sma200: float | None) -> str:
    """Plain-language read of price relative to the 50/200 MAs."""
    if sma200 is None:
        if sma50 is None:
            return 'Insufficient history'
        return 'Above 50' if price >= sma50 else 'Below 50'
    if price < sma200:
        return 'Bearish (below 200)'
    if sma50 is not None and price < sma50:
        return 'Pullback (above 200, below 50)'
    return 'Bullish (above 50 & 200)'


def _cross_state(close: pd.Series, settings: Settings) -> str:
    s50 = sma(close, settings.sma_short_window)
    s200 = sma(close, settings.sma_long_window)
    diff = (s50 - s200).dropna()
    if len(diff) < 2:
        return ''
    window = diff.tail(CROSS_LOOKBACK + 1)
    if len(window) < 2:
        return ''
    started_below = window.iloc[0] <= 0
    ends_above = window.iloc[-1] > 0
    if started_below and ends_above:
        return 'Golden (recent)'
    if not started_below and not ends_above:
        return 'Death (recent)'
    return 'Golden' if window.iloc[-1] > 0 else 'Death'


def _pct_diff(price: float, reference: float | None) -> float | None:
    if reference is None or reference == 0:
        return None
    return price / reference - 1.0


def _last(series: pd.Series) -> float | None:
    clean = series.dropna()
    return float(clean.iloc[-1]) if not clean.empty else None


def _to_float(token: str) -> float | None:
    try:
        return float(token.replace('$', '').replace(',', ''))
    except (TypeError, ValueError):
        return None
