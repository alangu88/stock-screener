from __future__ import annotations

from src.screener.sizing import PositionSizing, suggest_add_size


def test_normal_sizing_uses_risk_budget():
    # 1% of 100k = $1,000 risk; per-share risk = 100 - 90 = $10 -> 100 shares.
    sizing = suggest_add_size(100_000, 0.01, entry=100.0, stop=90.0)
    assert isinstance(sizing, PositionSizing)
    assert sizing.shares == 100
    assert sizing.dollars == 10_000.0
    assert sizing.risk_dollars == 1_000.0
    assert sizing.weight == 0.10  # $10k of $100k
    assert sizing.capped_by == 'risk'


def test_weight_cap_reduces_shares():
    # Risk budget alone wants 100 shares ($10k), but a 5% cap allows only $5k -> 50 shares.
    sizing = suggest_add_size(100_000, 0.01, entry=100.0, stop=90.0, max_position_weight=0.05)
    assert sizing is not None
    assert sizing.shares == 50
    assert sizing.dollars == 5_000.0
    assert sizing.weight == 0.05
    assert sizing.capped_by == 'weight'


def test_add_to_existing_uses_current_value():
    # Already hold $7k of a name; 10% cap on $100k leaves $3k room -> 30 shares at $100.
    sizing = suggest_add_size(
        100_000, 0.01, entry=100.0, stop=90.0, current_value=7_000.0
    )
    assert sizing is not None
    assert sizing.shares == 30
    assert sizing.dollars == 3_000.0
    assert sizing.weight == 0.10  # ($7k existing + $3k add) / $100k
    assert sizing.capped_by == 'weight'


def test_no_room_returns_zero_shares():
    # Position already at the weight cap -> nothing to add.
    sizing = suggest_add_size(
        100_000, 0.01, entry=100.0, stop=90.0, current_value=10_000.0
    )
    assert sizing is not None
    assert sizing.shares == 0
    assert sizing.dollars == 0.0
    assert sizing.risk_dollars == 0.0
    assert sizing.capped_by == 'weight'


def test_invalid_stop_returns_none():
    assert suggest_add_size(100_000, 0.01, entry=100.0, stop=100.0) is None
    assert suggest_add_size(100_000, 0.01, entry=90.0, stop=100.0) is None


def test_non_positive_account_value_returns_none():
    assert suggest_add_size(0, 0.01, entry=100.0, stop=90.0) is None
    assert suggest_add_size(-5, 0.01, entry=100.0, stop=90.0) is None


def test_shares_are_fractional_to_the_thousandth():
    # $1,000 risk over a $7 per-share risk = 142.857... shares -> rounded to 3 dp.
    sizing = suggest_add_size(100_000, 0.01, entry=100.0, stop=93.0, max_position_weight=1.0)
    assert sizing is not None
    assert sizing.shares == 142.857
    assert sizing.capped_by == 'risk'
