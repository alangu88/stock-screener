"""Backtesting tools for evaluating exit/stop strategies.

This package is research-only. It reuses the production entry pipeline
(``compute_features`` -> ``detect_setup`` -> ``build_trade_plan``) to generate
historically faithful entries, then simulates forward exits under different
stop strategies so their expectancy can be compared before any change is made
to the live methodology.
"""
