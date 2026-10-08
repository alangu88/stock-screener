"""Thin CLI entry point for the stock screener.

This keeps the project easy to run from the repository root while preserving the
existing Streamlit app under `src/app.py`.
"""

from __future__ import annotations

from src.app import run

if __name__ == '__main__':
    run()
