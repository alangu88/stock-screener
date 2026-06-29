"""Deterministic unit tests for the exit/stop simulator (no network)."""

from __future__ import annotations

from src.backtest.runner import Stats, summarize
from src.backtest.stops import (
    ScaleInParams,
    StopParams,
    TradeResult,
    simulate_scalein,
    simulate_trade,
)


def _flat_atr(n: int, value: float = 1.0) -> list[float]:
    return [value] * n


def test_initial_stop_hit_is_minus_one_r():
    # entry 100, stop 90 -> risk 10. First bar gaps to a low of 88 -> stop out.
    res = simulate_trade(
        entry=100.0,
        initial_stop=90.0,
        target=130.0,
        high=[101.0, 95.0],
        low=[99.0, 88.0],
        close=[100.0, 90.0],
        atr_prev=_flat_atr(2),
        params=StopParams(name='struct', target_exit=True),
    )
    assert res is not None
    assert res.exit_reason == 'stop'
    assert round(res.r_multiple, 6) == -1.0  # exited exactly at the initial stop


def test_target_exit_caps_at_reward_risk():
    # risk 10, target 130 -> 3R. Price runs straight to the target.
    res = simulate_trade(
        entry=100.0,
        initial_stop=90.0,
        target=130.0,
        high=[110.0, 132.0],
        low=[100.0, 120.0],
        close=[108.0, 130.0],
        atr_prev=_flat_atr(2),
        params=StopParams(name='struct', target_exit=True),
    )
    assert res is not None
    assert res.exit_reason == 'target'
    assert round(res.r_multiple, 6) == 3.0


def test_chandelier_lets_winner_run_then_trails_out():
    # No fixed target. Price climbs to 150 then reverses; a 2x ATR(=1) chandelier
    # trails just below the high-water mark and books most of the move.
    highs = [120.0, 140.0, 150.0, 145.0, 130.0]
    lows = [110.0, 130.0, 145.0, 130.0, 125.0]
    closes = [118.0, 138.0, 148.0, 132.0, 126.0]
    res = simulate_trade(
        entry=100.0,
        initial_stop=90.0,
        target=130.0,
        high=highs,
        low=lows,
        close=closes,
        atr_prev=_flat_atr(5, 1.0),
        params=StopParams(name='chand', chandelier_atr_mult=2.0, target_exit=False),
    )
    assert res is not None
    assert res.exit_reason == 'stop'
    # high_water reached 150; stop trails to ~148. Exit well above 3R.
    assert res.r_multiple > 4.0
    assert res.mfe_r >= 5.0


def test_breakeven_protects_after_one_r():
    # Reaches +1R (price 110), so the stop lifts to entry (100). A pullback to
    # 99 then stops out at breakeven (~0R) rather than the initial -1R.
    res = simulate_trade(
        entry=100.0,
        initial_stop=90.0,
        target=200.0,
        high=[111.0, 105.0],
        low=[101.0, 99.0],
        close=[110.0, 100.0],
        atr_prev=_flat_atr(2, 50.0),  # huge ATR disables the chandelier path
        params=StopParams(
            name='be', chandelier_atr_mult=None, breakeven_r=1.0, target_exit=False
        ),
    )
    assert res is not None
    assert res.exit_reason == 'stop'
    assert round(res.r_multiple, 6) == 0.0


def test_time_stop_exits_dead_money():
    # Never makes progress; after 3 bars the time stop closes at the last close.
    res = simulate_trade(
        entry=100.0,
        initial_stop=90.0,
        target=130.0,
        high=[101.0, 101.0, 101.0],
        low=[99.0, 99.0, 99.0],
        close=[100.0, 100.0, 100.0],
        atr_prev=_flat_atr(3, 50.0),
        params=StopParams(
            name='time', time_stop_bars=3, min_progress_r=0.5, target_exit=False
        ),
    )
    assert res is not None
    assert res.exit_reason == 'time'
    assert round(res.r_multiple, 6) == 0.0


def test_partial_books_profit_then_trails_remainder():
    # Take 1/2 at +2R (price 120), trail the rest which runs to 140 then reverses.
    res = simulate_trade(
        entry=100.0,
        initial_stop=90.0,
        target=500.0,
        high=[121.0, 140.0, 130.0],
        low=[110.0, 130.0, 120.0],
        close=[120.0, 138.0, 125.0],
        atr_prev=_flat_atr(3, 1.0),
        params=StopParams(
            name='partial',
            chandelier_atr_mult=2.0,
            partial_r=2.0,
            partial_frac=0.5,
            target_exit=False,
        ),
    )
    assert res is not None
    # 0.5 booked at +2R = 1.0R; remainder trails out above breakeven -> net > 2R.
    assert res.r_multiple > 2.0


def test_degenerate_inputs_return_none():
    assert simulate_trade(100.0, 100.0, 130.0, [101.0], [99.0], [100.0], [1.0],
                          StopParams(name='x')) is None
    assert simulate_trade(100.0, 90.0, 130.0, [], [], [], [],
                          StopParams(name='x')) is None


def test_scalein_full_size_matches_simulate_trade():
    # starter_frac=1.0 with no add must reproduce a one-unit trailing trade.
    highs = [120.0, 140.0, 150.0, 145.0, 130.0]
    lows = [110.0, 130.0, 145.0, 130.0, 125.0]
    closes = [118.0, 138.0, 148.0, 132.0, 126.0]
    base = simulate_trade(
        100.0, 90.0, 130.0, highs, lows, closes, _flat_atr(5, 1.0),
        StopParams(name='chand', chandelier_atr_mult=2.0, target_exit=False),
    )
    staged = simulate_scalein(
        100.0, 90.0, 130.0, highs, lows, closes, _flat_atr(5, 1.0),
        ScaleInParams(name='full', starter_frac=1.0, chandelier_atr_mult=2.0, target_exit=False),
    )
    assert base is not None and staged is not None
    assert round(staged.r_multiple, 9) == round(base.r_multiple, 9)


def test_scalein_unconfirmed_failure_loses_only_the_starter():
    # Price falls straight to the initial stop without ever reaching +0.5R, so
    # the add never fills: a half starter loses 0.5R instead of a full 1R.
    res = simulate_scalein(
        100.0, 90.0, 130.0,
        high=[101.0, 95.0],
        low=[99.0, 88.0],
        close=[100.0, 90.0],
        atr_prev=_flat_atr(2, 50.0),
        params=ScaleInParams(name='stage', starter_frac=0.5, add_trigger_r=0.5,
                             target_exit=True),
    )
    assert res is not None
    assert res.exit_reason == 'stop'
    assert round(res.r_multiple, 6) == -0.5


def test_scalein_confirmed_winner_pays_add_slippage():
    # Reaches +0.5R (price 105) so the add fills there, then runs to the 130
    # target (+3R). Full size would book 3.0R; staging books 3.0 - 0.5*0.5 = 2.75R.
    res = simulate_scalein(
        100.0, 90.0, 130.0,
        high=[106.0, 132.0],
        low=[100.0, 120.0],
        close=[105.0, 130.0],
        atr_prev=_flat_atr(2, 50.0),  # huge ATR disables the chandelier path
        params=ScaleInParams(name='stage', starter_frac=0.5, add_trigger_r=0.5,
                             add_raise_be=False, target_exit=True),
    )
    assert res is not None
    assert res.exit_reason == 'target'
    assert round(res.r_multiple, 6) == 2.75


def test_scalein_rejects_bad_starter_fraction():
    bars = ([101.0], [99.0], [100.0], [1.0])
    assert simulate_scalein(100.0, 90.0, 130.0, *bars,
                            ScaleInParams(name='x', starter_frac=0.0)) is None
    assert simulate_scalein(100.0, 90.0, 130.0, *bars,
                            ScaleInParams(name='x', starter_frac=1.5)) is None


def test_summarize_computes_expectancy_and_profit_factor():
    results = [
        TradeResult(2.0, 5, 'target', -0.3, 2.0),
        TradeResult(-1.0, 3, 'stop', -1.0, 0.4),
        TradeResult(3.0, 8, 'stop', -0.2, 4.0),
        TradeResult(-1.0, 2, 'stop', -1.0, 0.1),
    ]
    stats = summarize('v', results)
    assert isinstance(stats, Stats)
    assert stats.trades == 4
    assert round(stats.expectancy_r, 6) == 0.75  # (2 - 1 + 3 - 1) / 4
    assert stats.win_rate == 0.5
    assert round(stats.profit_factor, 6) == 2.5  # 5 / 2
    assert stats.r_per_bar > 0


def test_summarize_empty_is_zeroed():
    stats = summarize('empty', [])
    assert stats.trades == 0
    assert stats.expectancy_r == 0
