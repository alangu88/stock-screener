from src.screener.advisor import SCALE_2R, SCALE_EXTENDED
from src.screener.scaleout import (
    load_scaleout_ledger,
    save_scaleout_ledger,
    scaleout_key,
    update_scaleout_ledger,
)


def test_scaleout_key_normalises_account_and_ticker():
    assert scaleout_key('Roth IRA', 'lrcx') == 'Roth IRA|LRCX'
    assert scaleout_key(None, 'AAPL') == '|AAPL'


def test_load_missing_returns_empty(tmp_path):
    assert load_scaleout_ledger(tmp_path / 'missing.json') == {}


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / 'sub' / '.scaleout_ledger.json'
    ledger = {'Taxable|LRCX': {'shares': 0.118, 'rank': SCALE_EXTENDED}}
    save_scaleout_ledger(path, ledger)
    assert load_scaleout_ledger(path) == ledger


def test_first_sight_not_harvested_without_sell():
    records = [('Taxable|LRCX', 0.118, SCALE_EXTENDED)]
    harvested, ledger = update_scaleout_ledger(records, {})
    assert harvested == {'Taxable|LRCX': 0}
    assert ledger['Taxable|LRCX'] == {'shares': 0.118, 'rank': 0}


def test_bootstrap_harvested_from_existing_sell():
    records = [('Taxable|LRCX', 0.118, SCALE_EXTENDED)]
    harvested, ledger = update_scaleout_ledger(
        records, {}, first_seen_harvested={'Taxable|LRCX'}
    )
    assert harvested == {'Taxable|LRCX': SCALE_EXTENDED}
    assert ledger['Taxable|LRCX']['rank'] == SCALE_EXTENDED


def test_bootstrap_ignores_key_not_at_a_level():
    records = [('Taxable|GOOGL', 0.5, 0)]
    harvested, _ = update_scaleout_ledger(
        records, {}, first_seen_harvested={'Taxable|GOOGL'}
    )
    assert harvested == {'Taxable|GOOGL': 0}


def test_trim_at_level_marks_harvested():
    prev = {'Taxable|LRCX': {'shares': 0.177, 'rank': 0}}
    records = [('Taxable|LRCX', 0.118, SCALE_EXTENDED)]  # shares fell -> trim taken
    harvested, ledger = update_scaleout_ledger(records, prev)
    assert harvested['Taxable|LRCX'] == SCALE_EXTENDED
    assert ledger['Taxable|LRCX']['shares'] == 0.118


def test_trim_to_higher_level_raises_rank():
    prev = {'Taxable|LRCX': {'shares': 0.118, 'rank': SCALE_EXTENDED}}
    records = [('Taxable|LRCX', 0.08, SCALE_2R)]  # trimmed again at +2R
    harvested, _ = update_scaleout_ledger(records, prev)
    assert harvested['Taxable|LRCX'] == SCALE_2R


def test_non_scale_sell_does_not_harvest():
    prev = {'Taxable|LRCX': {'shares': 0.177, 'rank': 0}}
    records = [('Taxable|LRCX', 0.118, 0)]  # shares fell but not at any level
    harvested, _ = update_scaleout_ledger(records, prev)
    assert harvested['Taxable|LRCX'] == 0


def test_rebuild_resets_rank():
    prev = {'Taxable|LRCX': {'shares': 0.118, 'rank': SCALE_EXTENDED}}
    records = [('Taxable|LRCX', 0.25, SCALE_EXTENDED)]  # added shares -> fresh
    harvested, ledger = update_scaleout_ledger(records, prev)
    assert harvested['Taxable|LRCX'] == 0
    assert ledger['Taxable|LRCX']['rank'] == 0


def test_closed_position_drops_out():
    prev = {'Taxable|LRCX': {'shares': 0.118, 'rank': SCALE_EXTENDED}}
    harvested, ledger = update_scaleout_ledger([], prev)
    assert harvested == {}
    assert ledger == {}
