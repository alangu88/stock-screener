# AGENTS.md

Read natively by the GitHub Copilot cloud agent, Cursor, Codex, and any
other AGENTS.md-aware agent or tool. This file is a project-specific quick
reference — replace the placeholders below with real facts about this repo.

## Project

This repository is a Python-based stock screener for the S&P 500. It uses free Yahoo Finance data and a Streamlit UI to identify actionable setup candidates, rank them by quality, and generate structured trade plans with entry/stop/target levels.

Primary entry points:
- `src/app.py` — interactive Streamlit app for screening and charting.
- `scripts/generate_snapshot.py` — headless snapshot generator that writes a Markdown screen summary into the README.
- `src/screener/engine.py` — orchestration layer for the feature pipeline and ranking.
- `src/config.py` — environment-driven configuration for screener thresholds and runtime settings.

The project is research-focused and educational: it produces mechanical signals, not investment advice.

## Stack

- Python 3.11+
- Streamlit for the interactive dashboard
- pandas, numpy, plotly for data processing and charting
- yfinance + requests for market data retrieval
- pytest for tests
- ruff and mypy for linting/static analysis

Core runtime dependencies are declared in `pyproject.toml`; dev tools are included via the project optional `dev` extras.

## Commands

- Setup:
  - `python -m venv .venv`
  - `source .venv/bin/activate` (or `.venv\Scripts\activate` on Windows)
  - `pip install -r requirements.txt`
  - `pip install -r requirements-dev.txt` for test/lint tooling
- Run the app:
  - `streamlit run src/app.py`
- Generate the README snapshot:
  - `python scripts/generate_snapshot.py`
- Run tests:
  - `pytest`
  - `pytest --cov=src --cov-report=term-missing`
- Run lint/type checks:
  - `ruff check .`
  - `mypy`

## Conventions

- Keep the screener pipeline deterministic and data-driven; avoid ad hoc logic in the UI layer.
- Prefer changes in the underlying `src/screener/`, `src/analysis/`, and `src/data/` modules over one-off fixes in `src/app.py`.
- Respect the `SCREENER_*` configuration pattern in `src/config.py`; environment variables are the repo’s main runtime override mechanism.
- Keep market data and feature logic testable and isolated from UI concerns.
- Store cache and runtime state in the project’s configured cache directory rather than introducing global machine state.
- This project is a research tool: preserve the “mechanical signals only” framing in user-facing outputs and documentation.
- When editing code, follow the repo’s existing layout: `src/` for runtime code, `tests/` for unit/integration coverage, and `scripts/` for execution helpers.

## AI agent guidance

- Keep data fetches and technical calculations separated from decision logic.
- Prefer deterministic, pure calculations and continuous `0-100` scoring over hard binary cutoffs.
- Preserve the current pipeline: feature calculations → setup classification → trade-plan construction → ranking.
- Keep indicator logic in `src/analysis` and `src/screener`; new scoring primitives belong in `src/core`.
- Preserve type hints, docstrings, and testable behavior for new Python functions.
- Favor small, explainable changes over broad rewrites.
