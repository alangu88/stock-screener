from __future__ import annotations

import pandas as pd

from src.config import Settings
from src.data.market import earnings_soon, regime_risk_on

SETTINGS = Settings()


class _FakeClient:
    def __init__(self, spy_close=None, earnings=None):
        self._spy_close = spy_close
        self._earnings = earnings or {}

    def fetch_history(self, tickers, period):
        return {'SPY': pd.DataFrame({'Close': self._spy_close})}

    def fetch_earnings_dates(self, tickers):
        return {t: d for t, d in self._earnings.items() if t in tickers}


def test_regime_risk_on_above_long_ma():
    close = pd.Series([100.0] * 199 + [120.0])
    assert regime_risk_on(_FakeClient(spy_close=close), SETTINGS) is True


def test_regime_risk_off_below_long_ma():
    close = pd.Series([100.0] * 199 + [50.0])
    assert regime_risk_on(_FakeClient(spy_close=close), SETTINGS) is False


def test_regime_fails_open_on_short_history():
    assert regime_risk_on(_FakeClient(spy_close=pd.Series([1.0, 2.0])), SETTINGS) is True


def test_earnings_soon_filters_window():
    from datetime import UTC, datetime, timedelta

    soon = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()
    far = (datetime.now(UTC).date() + timedelta(days=40)).isoformat()
    client = _FakeClient(earnings={'AAA': soon, 'BBB': far})
    assert earnings_soon(client, ['AAA', 'BBB'], 7) == {'AAA'}


def test_earnings_soon_empty_when_disabled():
    assert earnings_soon(_FakeClient(earnings={'AAA': '2099-01-01'}), ['AAA'], 0) == set()
