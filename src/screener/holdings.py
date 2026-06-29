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

# Sleeve tags. Sleeve is ALWAYS the owner's explicit choice, never auto-derived
# from asset type -- e.g. a sector ETF like FSELX is a Satellite, not Core.
CORE = 'core'
SATELLITE = 'satellite'
SLEEVES = (CORE, SATELLITE)

# Directive key (in the private positions file) carrying total account value for
# risk-based sizing, e.g. ``account_value = 100000``.
ACCOUNT_VALUE_KEY = 'account_value'

# Directive key carrying free cash (e.g. SPAXX) available for new buys. May appear
# once per ``[Account]`` section; values are summed, e.g. ``cash = 7.18``.
CASH_KEY = 'cash'

MONITOR_COLUMNS = (
    'Ticker',
    'Account',
    'Sleeve',
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
    sleeve: str | None = None


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


@dataclass(frozen=True)
class AllocationStats:
    core_value: float        # market value of core-sleeve holdings
    satellite_value: float   # market value of satellite-sleeve holdings
    total_value: float       # core + satellite
    core_pct: float          # core_value / total_value (0..1)
    satellite_pct: float     # satellite_value / total_value (0..1)
    target_min: float        # lower bound of the core target band (0..1)
    target_max: float        # upper bound of the core target band (0..1)
    within_band: bool        # True when target_min <= core_pct <= target_max
    label: str               # 'On target' / 'Core light' / 'Core heavy'



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
        if _is_account_value_line(line):
            continue
        if _is_cash_line(line):
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


def parse_portfolio(text: str) -> list[PositionEntry]:
    """Parse the committed composition file (tickers + sleeve, no sizes).

    One ticker per line, optionally followed by a sleeve tag (``core`` or
    ``satellite``); the tag may appear before or after the ticker and is
    matched case-insensitively. ``#`` starts a comment and ``[Account Name]``
    opens a section, exactly like :func:`parse_positions`. Lines carry **no**
    share counts or prices -- this file is safe to commit. Example::

        [Taxable]
        VTI, core
        VXUS, core
        FSELX, satellite     # sector ETF is a satellite, not core

    The sleeve defaults to ``satellite`` when omitted. Duplicate tickers within
    an account keep the first occurrence; the same ticker may appear under
    different accounts.
    """
    entries: list[PositionEntry] = []
    seen: set[tuple[str | None, str]] = set()
    current_account: str | None = None
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('[') and line.endswith(']'):
            current_account = line[1:-1].strip() or None
            continue
        tokens = [p for p in line.replace(',', ' ').replace('\t', ' ').split() if p]
        sleeve = SATELLITE
        symbol = ''
        for token in tokens:
            low = token.lower()
            if low in SLEEVES:
                sleeve = low
            elif not symbol:
                symbol = normalize_ticker(token)
        if not symbol:
            continue
        key = (current_account, symbol)
        if key in seen:
            continue
        seen.add(key)
        entries.append(PositionEntry(symbol, account=current_account, sleeve=sleeve))
    return entries


def parse_account_value(text: str) -> float | None:
    """Return the ``account_value`` directive from a positions file, if present.

    Recognizes a line like ``account_value = 100000`` or ``account_value: 95,000``
    (``$`` and thousands separators are tolerated). Returns ``None`` when absent
    or unparseable.
    """
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        value = _account_value_directive(line)
        if value is not None:
            return value
    return None


def parse_cash(text: str) -> float | None:
    """Return total free cash from ``cash`` directives, if any are present.

    A ``cash = N`` line may appear once per ``[Account]`` section (e.g. the SPAXX
    balance in each Fidelity account); all such lines are summed into a single
    total used for buy-sizing. ``$`` and thousands separators are tolerated, and
    a single line may itself be a ``+``-separated sum. Returns ``None`` when no
    ``cash`` directive exists so callers can fall back to inferring cash.
    """
    total = 0.0
    found = False
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        value = _directive_value(line, CASH_KEY)
        if value is not None:
            total += value
            found = True
    return total if found else None


def merge_holdings(
    portfolio: list[PositionEntry],
    positions: list[PositionEntry],
) -> list[PositionEntry]:
    """Combine committed composition with private sizing into full holdings.

    Sleeve and membership come from ``portfolio`` (the committed file); cost
    basis and shares come from ``positions`` (the private file), joined on
    ``(account, ticker)``. Tickers present only in ``positions`` (held but not
    yet published) are appended with a default ``satellite`` sleeve.
    """
    sizes = {(p.account, p.ticker): p for p in positions}
    merged: list[PositionEntry] = []
    used: set[tuple[str | None, str]] = set()
    for entry in portfolio:
        key = (entry.account, entry.ticker)
        used.add(key)
        sized = sizes.get(key)
        merged.append(
            PositionEntry(
                ticker=entry.ticker,
                entry_price=sized.entry_price if sized else None,
                shares=sized.shares if sized else None,
                account=entry.account,
                sleeve=entry.sleeve or SATELLITE,
            )
        )
    for entry in positions:
        key = (entry.account, entry.ticker)
        if key in used:
            continue
        used.add(key)
        merged.append(
            PositionEntry(
                ticker=entry.ticker,
                entry_price=entry.entry_price,
                shares=entry.shares,
                account=entry.account,
                sleeve=entry.sleeve or SATELLITE,
            )
        )
    return merged


def export_manifest(entries: list[PositionEntry]) -> str:
    """Render holdings as committable composition text (tickers + sleeve only).

    Sizes (shares, cost basis) are intentionally dropped so the result is safe
    to commit. Output mirrors the :func:`parse_portfolio` format, grouped by
    account in first-seen order.
    """
    grouped: dict[str | None, list[PositionEntry]] = {}
    order: list[str | None] = []
    for entry in entries:
        if entry.account not in grouped:
            grouped[entry.account] = []
            order.append(entry.account)
        grouped[entry.account].append(entry)

    out = [
        '# Portfolio composition (safe to commit) -- tickers + sleeve only, no sizes.',
        '# Auto-generated from your positions; edit and re-publish from the app.',
    ]
    for account in order:
        out.append('')
        if account:
            out.append(f'[{account}]')
        for entry in grouped[account]:
            out.append(f'{entry.ticker}, {entry.sleeve or SATELLITE}')
    return '\n'.join(out) + '\n'


def _is_account_value_line(line: str) -> bool:
    """True when a line is an ``account_value`` directive (by key), valid or not.

    Detecting by key -- not by a parseable value -- means a malformed value never
    leaks through and gets mistaken for a ticker named ``ACCOUNT_VALUE``.
    """
    return _is_directive_line(line, ACCOUNT_VALUE_KEY)


def _is_cash_line(line: str) -> bool:
    """True when a line is a ``cash`` directive (by key), valid or not."""
    return _is_directive_line(line, CASH_KEY)


def _is_directive_line(line: str, key: str) -> bool:
    """True when ``line`` starts with ``key`` followed by ``=`` or ``:``."""
    if not line:
        return False
    low = line.lower()
    if not low.startswith(key):
        return False
    rest = line[len(key):].lstrip()
    return rest[:1] in ('=', ':')


def _account_value_directive(line: str) -> float | None:
    """Parse an ``account_value = N`` directive line, else ``None``.

    The value may be a single number or a sum of ``+``-separated numbers (handy
    for adding several account balances, e.g. ``account_value = 2310 + 5269``).
    ``$`` and thousands separators are tolerated. Returns ``None`` if the line is
    not a directive or no term parses.
    """
    return _directive_value(line, ACCOUNT_VALUE_KEY)


def _directive_value(line: str, key: str) -> float | None:
    """Parse a ``<key> = N`` directive line, else ``None``.

    The value may be a single number or a sum of ``+``-separated numbers. ``$``
    and thousands separators are tolerated. Returns ``None`` if the line is not a
    directive for ``key`` or no term parses.
    """
    if not _is_directive_line(line, key):
        return None
    rest = line[len(key):].lstrip()[1:].strip()
    terms = [_to_float(term) for term in rest.split('+')]
    valid = [t for t in terms if t is not None]
    if not valid:
        return None
    return sum(valid)


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
    row['Sleeve'] = entry.sleeve
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


def allocation_summary(
    monitor: pd.DataFrame,
    core_min: float,
    core_max: float,
) -> AllocationStats | None:
    """Summarize Core vs Satellite allocation against the target band.

    Core value is the sum of ``Value`` for rows tagged ``core`` in the
    ``Sleeve`` column; everything else sized counts as Satellite. Returns
    ``None`` when there are no sized positions.
    """
    if 'Sleeve' not in monitor.columns:
        return None
    sized = monitor.loc[monitor['Value'].notna(), ['Sleeve', 'Value']].copy()
    sized = sized[sized['Value'] > 0]
    if sized.empty:
        return None

    total_value = float(sized['Value'].sum())
    is_core = sized['Sleeve'].astype('string').str.lower() == CORE
    core_value = float(sized.loc[is_core, 'Value'].sum())
    satellite_value = total_value - core_value
    core_pct = core_value / total_value
    satellite_pct = satellite_value / total_value

    if core_pct < core_min:
        label = 'Core light'
    elif core_pct > core_max:
        label = 'Core heavy'
    else:
        label = 'On target'

    return AllocationStats(
        core_value=core_value,
        satellite_value=satellite_value,
        total_value=total_value,
        core_pct=core_pct,
        satellite_pct=satellite_pct,
        target_min=core_min,
        target_max=core_max,
        within_band=core_min <= core_pct <= core_max,
        label=label,
    )


def count_individual_stocks(monitor: pd.DataFrame, etf_tickers: set[str]) -> int:
    """Count single-company Satellite holdings (ETFs excluded).

    Used to police the diversification cap on individual names. Tickers present
    in ``etf_tickers`` are treated as funds and excluded from the count; Core
    holdings (typically broad index funds) are excluded too.
    """
    if 'Sleeve' not in monitor.columns:
        sleeves = pd.Series([None] * len(monitor), index=monitor.index)
    else:
        sleeves = monitor['Sleeve'].astype('string').str.lower()
    etfs = {t.upper() for t in etf_tickers}
    count = 0
    for ticker, sleeve in zip(monitor['Ticker'], sleeves, strict=False):
        if sleeve == CORE:
            continue
        if str(ticker).upper() in etfs:
            continue
        count += 1
    return count


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
