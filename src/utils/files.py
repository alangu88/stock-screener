"""Filesystem read helpers for headless scripts (no Streamlit dependency).

``src/ui/files.py`` owns the same idea for the app, but it imports Streamlit, so
the CLI scripts use this lightweight module instead to avoid pulling a UI
framework into batch jobs.
"""

from __future__ import annotations

from pathlib import Path


def read_text_or_empty(path: Path) -> str:
    """Return a file's UTF-8 text, or ``''`` when the file does not exist."""
    return path.read_text(encoding='utf-8') if path.exists() else ''
