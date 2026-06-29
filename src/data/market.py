"""Best-effort market-state helpers (regime and earnings proximity).

Both fail open: any data gap returns the permissive result so a Yahoo hiccup
never blocks the report or the app.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from src.config import Settings
from src.data.yahoo_client import YahooFinanceClient

_EASTERN = ZoneInfo('America/New_York')
_MARKET_OPEN = time(9, 30)
_MARKET_CLOSE = time(16, 0)


def market_is_open(now: datetime | None = None) -> bool:
    """True during regular US equity trading hours (Mon-Fri, 9:30-16:00 ET).

    Holidays are not accounted for: at worst this triggers a harmless data
    refresh on a market holiday. ``now`` is mainly for testing; when omitted the
    current Eastern time is used.
    """
    current = (now or datetime.now(_EASTERN)).astimezone(_EASTERN)
    if current.weekday() >= 5:
        return False
    return _MARKET_OPEN <= current.time() < _MARKET_CLOSE


def regime_risk_on(client: YahooFinanceClient, settings: Settings) -> bool:
    """True when SPY is at/above its long SMA (risk-on); fail-open on data gaps."""
    try:
        close = client.fetch_history(['SPY'], period='2y')['SPY']['Close'].dropna()
        if len(close) < settings.sma_long_window:
            return True
        return float(close.iloc[-1]) >= float(close.tail(settings.sma_long_window).mean())
    except Exception:
        return True


def earnings_soon(client: YahooFinanceClient, tickers: list[str], days: int) -> set[str]:
    """Tickers reporting within ``days``; best-effort, empty on any data issue."""
    soon: set[str] = set()
    if not tickers or days <= 0:
        return soon
    today = datetime.now(UTC).date()
    for ticker, raw in client.fetch_earnings_dates(tickers).items():
        try:
            when = datetime.fromisoformat(str(raw)[:10]).date()
        except ValueError:
            continue
        if 0 <= (when - today).days <= days:
            soon.add(ticker)
    return soon
