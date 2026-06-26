import pandas as pd

from src.data.universe import UniverseResult
from src.screener.engine import FilterConfig, ScreenerEngine


class _FakeFundamental:
    def __init__(self, ticker: str, company_name: str, market_cap: float, pe: float, rev: float, exchange: str):
        self.ticker = ticker
        self.company_name = company_name
        self.market_cap = market_cap
        self.pe_ratio = pe
        self.revenue_growth = rev
        self.exchange = exchange


def _breakout_close() -> list[float]:
    """Long uptrend, a deep base that tightens near the highs, then a breakout."""
    vals = [100.0 + i for i in range(200)]            # uptrend 100 -> 299
    vals += [300.0 - j * (20.0 / 29) for j in range(30)]   # pullback 300 -> 280
    vals += [280.0 + j * (26.0 / 19) for j in range(20)]   # recovery 280 -> 306
    vals += [305.0, 306.0, 307.0, 306.0, 305.0, 306.0, 307.0, 306.0, 307.0]  # tight handle
    vals.append(313.0)                                 # breakout bar
    return vals[:260]


class FakeClient:
    def fetch_fundamentals(self, tickers, force_refresh=False):
        return {
            t: _FakeFundamental(t, f'Company {t}', 1_000_000_000, 20.0, 0.12, 'NMS')
            for t in tickers
        }

    def filter_allowed_exchanges(self, fundamentals):
        return list(fundamentals.keys()), []

    def fetch_history(self, tickers, period='2y', interval='1d', force_refresh=False):
        idx = pd.date_range('2024-01-01', periods=260, freq='B')
        data = {}
        for t in tickers:
            if t == 'SPY':
                close = pd.Series([300.0 + i * 0.03 for i in range(260)], index=idx)
            else:
                close = pd.Series(_breakout_close(), index=idx)
            vol = pd.Series([900_000.0] * 260, index=idx)
            vol.iloc[-1] = 1_600_000.0  # breakout-day volume expansion
            data[t] = pd.DataFrame({'Close': close, 'Volume': vol}, index=idx)
        return data


def test_screener_pipeline_returns_actionable_breakouts():
    engine = ScreenerEngine(client=FakeClient())
    universe = UniverseResult(tickers=['AAA', 'BBB'], companies={'AAA': 'A Co', 'BBB': 'B Co'})
    cfg = FilterConfig(min_confidence=45.0, min_reward_risk=1.5, min_avg_volume=100)

    out = engine.screen(universe, cfg)

    assert not out.empty
    assert {'Ticker', 'Setup', 'Confidence', 'Entry', 'Stop', 'Target', 'R/R'}.issubset(out.columns)
    assert (out['Setup'] == 'Breakout').all()
    # Every surviving row must be asymmetric and confident by construction.
    assert (out['R/R'] >= cfg.min_reward_risk).all()
    assert (out['Confidence'] >= 45.0).all()
    # Entry/stop/target form a valid long structure.
    assert (out['Stop'] < out['Entry']).all()
    assert (out['Entry'] < out['Target']).all()


def test_high_confidence_gate_filters_everything():
    engine = ScreenerEngine(client=FakeClient())
    universe = UniverseResult(tickers=['AAA'], companies={'AAA': 'A Co'})
    cfg = FilterConfig(min_confidence=99.0, min_reward_risk=1.5, min_avg_volume=100)

    out = engine.screen(universe, cfg)

    assert out.empty
