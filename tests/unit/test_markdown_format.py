from __future__ import annotations

import math

from src.export.markdown_format import is_missing, number, table, text


def test_is_missing() -> None:
    assert is_missing(None)
    assert is_missing(float('nan'))
    assert not is_missing(0)
    assert not is_missing('')


def test_number_formats_and_scales() -> None:
    assert number(1234.5, ',.2f', prefix='$') == '$1,234.50'
    assert number(0.1234, '.2f', scale=100, suffix='%') == '12.34%'
    assert number(3.0, '.0f') == '3'


def test_number_missing_placeholder() -> None:
    assert number(None) == '\u2014'
    assert number(float('nan'), missing='-') == '-'
    assert not math.isnan(0.0) and number(0.0, '.2f') == '0.00'


def test_text_missing() -> None:
    assert text(None) == '\u2014'
    assert text('', missing='-') == '-'
    assert text('AAPL') == 'AAPL'


def test_table_renders_rows() -> None:
    out = table(['A', 'B'], [['1', '2'], ['3', '4']])
    assert out.splitlines() == [
        '| A | B |',
        '| --- | --- |',
        '| 1 | 2 |',
        '| 3 | 4 |',
    ]


def test_table_empty_uses_placeholder() -> None:
    assert table(['A'], []) == '_None._'
    assert table(['A'], [], empty='nothing') == 'nothing'
