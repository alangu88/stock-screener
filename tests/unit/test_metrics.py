from src.backtest.metrics import cagr, drawdown, equity_curve
from src.config import Settings


def test_drawdown_is_zero_for_monotonic_curve():
    assert drawdown([1.0, 1.1, 1.2, 1.5]) == 0.0


def test_drawdown_reports_worst_peak_to_trough():
    # Peak 2.0 -> trough 1.0 is a -50% drawdown.
    assert drawdown([1.0, 2.0, 1.0, 1.8]) == -0.5


def test_cagr_matches_compounding():
    # Doubling over 2 years -> ~41.4% CAGR.
    assert abs(cagr(1.0, 4.0, 2.0) - 1.0) < 1e-9


def test_cagr_guards_degenerate_spans():
    assert cagr(1.0, 2.0, 0.0) == 0.0
    assert cagr(0.0, 2.0, 1.0) == 0.0


def test_equity_curve_compounds_sequential_winners():
    settings = Settings()
    # Two non-overlapping winning trades, each +2R at max conviction.
    trades = [
        (0, 1, 2.0, 100.0),
        (2, 3, 2.0, 100.0),
    ]
    final, curve = equity_curve(trades, settings, max_concurrent=1, cost=0.0)
    assert curve[0] == 1.0
    assert final > 1.0
    assert curve[-1] == final


def test_equity_curve_respects_concurrency_cap():
    settings = Settings()
    # Both trades open on day 0; a cap of 1 must skip the second entry.
    overlapping = [
        (0, 5, 3.0, 100.0),
        (0, 5, 3.0, 100.0),
    ]
    capped, _ = equity_curve(overlapping, settings, max_concurrent=1, cost=0.0)
    uncapped, _ = equity_curve(overlapping, settings, max_concurrent=2, cost=0.0)
    assert uncapped > capped
