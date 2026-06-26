"""Unit tests for the Markdown snapshot renderer."""

from __future__ import annotations

import pandas as pd
import pytest

from src.export.markdown_export import (
    END_MARKER,
    START_MARKER,
    build_snapshot_markdown,
    build_unavailable_markdown,
    inject_between_markers,
    results_to_markdown,
    sleeve_summary_to_markdown,
)
from src.screener.portfolio import PortfolioConfig, assign_portfolio
from src.screener.setups import BREAKOUT, CONTRACTION, PULLBACK


def _row(ticker, setup, confidence, risk, market_cap, trend, rank, rr=2.0):
    return {
        'Ticker': ticker,
        'Setup': setup,
        'Confidence': confidence,
        'Rank Score': rank,
        'Entry': 100.0,
        'Stop': 100.0 * (1 - risk),
        'Target': 100.0 * (1 + risk * rr),
        'Risk %': risk,
        'Reward %': risk * rr,
        'R/R': rr,
        'Market Cap': market_cap,
        'Trend Score': trend,
        'Market Context': 'Risk-On',
    }


def _frame():
    rows = [
        _row('AAA', PULLBACK, 88, 0.04, 1.2e12, 0.95, 90.0),
        _row('BBB', CONTRACTION, 80, 0.03, 4e11, 0.85, 80.0),
        _row('CCC', PULLBACK, 72, 0.05, 9e10, 0.70, 70.0),
        _row('DDD', BREAKOUT, 60, 0.08, 6e9, 0.40, 55.0),
    ]
    return assign_portfolio(pd.DataFrame(rows), PortfolioConfig())


def test_results_to_markdown_has_header_and_limited_rows():
    md = results_to_markdown(_frame(), limit=2)
    lines = md.splitlines()
    assert lines[0].startswith('| Ticker |')
    assert set('-|') >= set(lines[1].replace(' ', ''))  # divider row
    data_rows = [ln for ln in lines[2:] if ln.startswith('|')]
    assert len(data_rows) == 2  # respects limit
    assert 'AAA' in md and 'BBB' in md  # top two by rank score


def test_results_to_markdown_handles_empty():
    md = results_to_markdown(pd.DataFrame())
    assert 'No symbols matched' in md


def test_sleeve_summary_to_markdown_lists_sleeves():
    md = sleeve_summary_to_markdown(_frame())
    assert 'Core' in md and 'Satellite' in md and 'Total' in md


def test_build_snapshot_markdown_includes_badges_and_sections():
    md = build_snapshot_markdown(
        _frame(), generated_at='2026-06-26 22:30 UTC', regime_label='Risk-On', symbols_screened=120
    )
    assert 'img.shields.io/badge/matches-4' in md
    assert 'regime-Risk--On' in md  # hyphen escaped for shields.io
    assert 'screened-120' in md
    assert 'Top picks' in md
    assert 'Portfolio sleeves' in md
    assert 'research only' in md


def test_build_snapshot_markdown_handles_empty_frame():
    md = build_snapshot_markdown(
        pd.DataFrame(), generated_at='2026-06-26 22:30 UTC', regime_label='Unknown', symbols_screened=0
    )
    assert 'matches-0' in md
    assert 'No symbols matched' in md


def test_inject_between_markers_replaces_only_marked_region():
    text = f'top\n{START_MARKER}\nOLD\n{END_MARKER}\nbottom'
    out = inject_between_markers(text, 'NEW')
    assert 'OLD' not in out
    assert 'NEW' in out
    assert out.startswith('top')
    assert out.endswith('bottom')
    assert out.count(START_MARKER) == 1 and out.count(END_MARKER) == 1


def test_inject_between_markers_is_idempotent():
    text = f'a\n{START_MARKER}\nx\n{END_MARKER}\nb'
    once = inject_between_markers(text, 'BLOCK')
    twice = inject_between_markers(once, 'BLOCK')
    assert once == twice


def test_inject_between_markers_requires_markers():
    with pytest.raises(ValueError):
        inject_between_markers('no markers here', 'BLOCK')


def test_build_unavailable_markdown_is_valid_block():
    md = build_unavailable_markdown(generated_at='2026-06-26 22:30 UTC', reason='ReadTimeout')
    assert 'temporarily unavailable' in md
    assert 'ReadTimeout' in md
