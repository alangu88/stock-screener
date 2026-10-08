.PHONY: help install dev run snapshot test lint typecheck clean

PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYTHON_VENV := $(VENV)/bin/python

help:
	@printf "Stock Screener make targets:\n"
	@printf "  make install      Create venv and install runtime dependencies\n"
	@printf "  make dev          Install runtime + dev dependencies\n"
	@printf "  make run          Launch the Streamlit app\n"
	@printf "  make snapshot     Generate the README screen snapshot\n"
	@printf "  make test         Run the unit/integration test suite\n"
	@printf "  make lint         Run Ruff lint checks\n"
	@printf "  make typecheck    Run mypy\n"
	@printf "  make clean        Remove local cache and virtual environment\n"
	@printf "  make help         Show this help text\n"

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -r requirements.txt

dev:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

run:
	$(PYTHON_VENV) -m streamlit run src/app.py

snapshot:
	$(PYTHON_VENV) scripts/generate_snapshot.py

test:
	$(PYTHON_VENV) -m pytest -q

lint:
	$(PYTHON_VENV) -m ruff check .

typecheck:
	$(PYTHON_VENV) -m mypy

clean:
	rm -rf $(VENV) .cache
