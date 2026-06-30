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


def test_analyze_returns_row_per_ticker_with_actionable_flag():
    engine = ScreenerEngine(client=FakeClient())
    universe = UniverseResult(tickers=['AAA', 'BBB'], companies={'AAA': 'A Co', 'BBB': 'B Co'})
    cfg = FilterConfig(min_confidence=45.0, min_reward_risk=1.5, min_avg_volume=100)

    out = engine.analyze(universe, cfg)

    assert list(out['Ticker']) == ['AAA', 'BBB']
    assert 'Actionable' in out.columns
    # The breakout construction clears the loose gates for both names.
    assert out['Actionable'].all()
    assert {'Entry', 'Stop', 'Target', 'R/R', 'Confidence'}.issubset(out.columns)


class _RiskOffClient(FakeClient):
    """Same breakouts as ``FakeClient`` but a benchmark in a risk-off downtrend."""

    def fetch_history(self, tickers, period='2y', interval='1d', force_refresh=False):
        data = super().fetch_history(tickers, period, interval, force_refresh)
        if 'SPY' in data:
            idx = data['SPY'].index
            # Falling SPY: last close sits below its 200-day SMA (risk-off).
            data['SPY']['Close'] = pd.Series(
                [400.0 - i * 0.3 for i in range(len(idx))], index=idx
            )
        return data


def test_require_regime_suppresses_adds_when_risk_off():
    engine = ScreenerEngine(client=_RiskOffClient())
    universe = UniverseResult(tickers=['AAA', 'BBB'], companies={'AAA': 'A Co', 'BBB': 'B Co'})

    gated = engine.screen(
        universe,
        FilterConfig(min_confidence=45.0, min_reward_risk=1.5,
                     min_avg_volume=100, require_regime=True),
    )
    ungated = engine.screen(
        universe,
        FilterConfig(min_confidence=45.0, min_reward_risk=1.5,
                     min_avg_volume=100, require_regime=False),
    )

    # The same breakouts qualify without the gate, but the risk-off regime
    # suppresses every add once the gate is on.
    assert not ungated.empty
    assert gated.empty


def test_require_regime_allows_adds_when_risk_on():
    engine = ScreenerEngine(client=FakeClient())
    universe = UniverseResult(tickers=['AAA', 'BBB'], companies={'AAA': 'A Co', 'BBB': 'B Co'})

    out = engine.screen(
        universe,
        FilterConfig(min_confidence=45.0, min_reward_risk=1.5,
                     min_avg_volume=100, require_regime=True),
    )

    # SPY is in an uptrend here, so the regime gate is a no-op.
    assert not out.empty



def test_analyze_includes_non_actionable_rows():
    engine = ScreenerEngine(client=FakeClient())
    universe = UniverseResult(tickers=['AAA'], companies={'AAA': 'A Co'})
    # A gate so tight nothing is actionable -- but analyze still returns the row.
    cfg = FilterConfig(min_confidence=99.0, min_reward_risk=1.5, min_avg_volume=100)

    out = engine.analyze(universe, cfg)

    assert list(out['Ticker']) == ['AAA']
    assert out['Actionable'].tolist() == [False]
    # Plan levels are still populated for the held/analysed name.
    assert out.iloc[0]['Entry'] is not None


def test_analyze_empty_universe_returns_empty_frame():
    engine = ScreenerEngine(client=FakeClient())
    cfg = FilterConfig(min_confidence=45.0, min_reward_risk=1.5, min_avg_volume=100)

    out = engine.analyze(UniverseResult(tickers=[], companies={}), cfg)

    assert out.empty
    assert 'Actionable' in out.columns

