from __future__ import annotations

from src.data.yahoo_client import FundHoldings
from src.screener.exposure import look_through_exposure, normalize_symbol


def _fund(ticker: str, holdings: dict[str, float], names: dict[str, str] | None = None) -> FundHoldings:
    return FundHoldings(
        ticker=ticker,
        holdings=holdings,
        names=names or {},
        top_weight_total=sum(holdings.values()),
    )


def test_direct_and_fund_exposure_combine_for_the_same_symbol():
    fund = _fund('FUND', {'NVDA': 0.20, 'AAPL': 0.10}, {'NVDA': 'NVIDIA', 'AAPL': 'Apple'})
    holdings = [('NVDA', 100.0), ('FUND', 500.0)]

    exposures, tail = look_through_exposure(holdings, {'FUND': fund}, {'FUND'}, account_value=1000.0)

    by_symbol = {e.symbol: e for e in exposures}
    nvda = by_symbol['NVDA']
    assert nvda.direct_value == 100.0
    assert nvda.fund_value == 100.0  # 500 * 0.20
    assert nvda.total_value == 200.0
    assert nvda.weight == 0.20
    assert nvda.name == 'NVIDIA'

    aapl = by_symbol['AAPL']
    assert aapl.direct_value == 0.0
    assert aapl.fund_value == 50.0  # 500 * 0.10
    # Untracked tail = 500 * (1 - 0.30)
    assert tail == 350.0
    # Sorted by total value descending.
    assert exposures[0].symbol == 'NVDA'


def test_fund_without_lookthrough_data_goes_entirely_to_tail():
    holdings = [('FUND', 400.0), ('MSFT', 100.0)]

    exposures, tail = look_through_exposure(holdings, {}, {'FUND'}, account_value=500.0)

    symbols = {e.symbol for e in exposures}
    assert symbols == {'MSFT'}
    assert tail == 400.0


def test_zero_and_missing_values_are_ignored():
    holdings = [('AAPL', 0.0), ('MSFT', None), ('NVDA', 50.0)]

    exposures, tail = look_through_exposure(holdings, {}, set(), account_value=100.0)

    assert [e.symbol for e in exposures] == ['NVDA']
    assert tail == 0.0


def test_weights_are_zero_when_account_value_is_non_positive():
    exposures, _ = look_through_exposure([('NVDA', 50.0)], {}, set(), account_value=0.0)
    assert exposures[0].weight == 0.0


def test_direct_holdings_are_labelled_from_the_name_lookup():
    holdings = [('MSFT', 100.0), ('2330.TW', 50.0)]
    name_lookup = {'MSFT': 'Microsoft', 'TSM': 'Taiwan Semiconductor'}

    exposures, _ = look_through_exposure(
        holdings, {}, set(), account_value=1000.0, name_lookup=name_lookup
    )

    by_symbol = {e.symbol: e for e in exposures}
    assert by_symbol['MSFT'].name == 'Microsoft'
    # Lookup resolves via the canonical (normalised) ticker too.
    assert by_symbol['TSM'].name == 'Taiwan Semiconductor'


def test_cross_listed_fund_symbol_merges_with_direct_holding():
    # VXUS-style local line 2330.TW is the same company as the directly held TSM.
    fund = _fund('VXUS', {'2330.TW': 0.04}, {'2330.TW': 'Taiwan Semiconductor Manufacturing Co Ltd'})
    holdings = [('TSM', 46.0), ('VXUS', 1000.0)]

    exposures, _ = look_through_exposure(holdings, {'VXUS': fund}, {'VXUS'}, account_value=2000.0)

    by_symbol = {e.symbol: e for e in exposures}
    assert '2330.TW' not in by_symbol
    tsm = by_symbol['TSM']
    assert tsm.direct_value == 46.0
    assert tsm.fund_value == 40.0  # 1000 * 0.04
    assert tsm.total_value == 86.0
    assert tsm.name == 'Taiwan Semiconductor Manufacturing Co Ltd'


def test_normalize_symbol_is_identity_for_us_tickers():
    assert normalize_symbol('NVDA') == 'NVDA'
    assert normalize_symbol('2330.TW') == 'TSM'
    assert normalize_symbol('') == ''


def test_alphabet_share_classes_merge():
    # GOOG (Class C) collapses into the directly held GOOGL (Class A).
    assert normalize_symbol('GOOG') == 'GOOGL'
    fund = _fund('FUND', {'GOOG': 0.10}, {'GOOG': 'Alphabet Inc Class C'})
    holdings = [('GOOGL', 100.0), ('FUND', 500.0)]

    exposures, _ = look_through_exposure(holdings, {'FUND': fund}, {'FUND'}, account_value=1000.0)

    by_symbol = {e.symbol: e for e in exposures}
    assert 'GOOG' not in by_symbol
    googl = by_symbol['GOOGL']
    assert googl.direct_value == 100.0
    assert googl.fund_value == 50.0  # 500 * 0.10
    assert googl.total_value == 150.0

