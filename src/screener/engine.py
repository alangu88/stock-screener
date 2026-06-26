from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.analysis.features import compute_features
from src.config import Settings
from src.data.universe import UniverseResult
from src.data.yahoo_client import Fundamentals, YahooFinanceClient
from src.screener.backtest import BacktestParams, Trade, backtest_universe
from src.screener.portfolio import PortfolioConfig, assign_portfolio
from src.screener.ranking import (
    MarketContext,
    assess_market_context,
    composite_rank,
    confidence_score,
)
from src.screener.result import RESULT_COLUMNS
from src.screener.setups import AVOID, detect_setup
from src.screener.strategy import StrategyConfig
from src.screener.trade_plan import build_trade_plan

HISTORY_PERIOD = '2y'
BENCHMARK_TICKER = 'SPY'

# Columns emitted by ``ScreenerEngine.analyze`` -- the ungated per-ticker view.
# These mirror the raw row from ``_result_row`` (before portfolio assignment)
# plus an ``Actionable`` flag indicating whether the screen gates passed.
ANALYSIS_COLUMNS: tuple[str, ...] = (
    'Ticker',
    'Company Name',
    'Setup',
    'Confidence',
    'Rank Score',
    'Entry',
    'Stop',
    'Target',
    'Risk %',
    'Reward %',
    'R/R',
    'Reason',
    'Key Factors',
    'Risks',
    'Trend Score',
    'RS Outperformance',
    'Rel Volume',
    'Market Cap',
    'PE Ratio',
    'Revenue Growth',
    'Price',
    'Market Context',
    'Actionable',
)


@dataclass
class _TickerAnalysis:
    """Per-ticker compute output shared by ``screen`` and ``analyze``."""

    features: object
    setup: object
    plan: object
    confidence: float
    fundamental: Fundamentals
    company_name: str


@dataclass
class FilterConfig:
    """User-facing screening gates applied on top of the strategy.

    These keep only high-quality, actionable candidates: an identified setup
    (never ``Avoid``), sufficient confidence, an asymmetric reward/risk, and
    tradable liquidity.
    """

    min_confidence: float = 45.0
    min_reward_risk: float = 1.5
    min_avg_volume: int = 500_000
    setups: tuple[str, ...] | None = None  # None => all actionable setups

    @classmethod
    def from_settings(cls, settings: Settings) -> FilterConfig:
        return cls(min_avg_volume=settings.min_avg_volume)


class ScreenerEngine:
    """Orchestrates retrieval -> features -> setup -> plan -> ranking."""

    def __init__(
        self,
        client: YahooFinanceClient,
        strategy: StrategyConfig | None = None,
        portfolio: PortfolioConfig | None = None,
    ):
        self.client = client
        self.strategy = strategy or StrategyConfig()
        self.portfolio = portfolio or PortfolioConfig()

    def screen(
        self,
        universe: UniverseResult,
        config: FilterConfig,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        if not universe.tickers:
            return _empty_frame()

        fundamentals = self.client.fetch_fundamentals(universe.tickers, force_refresh=force_refresh)
        allowed, _ = self.client.filter_allowed_exchanges(fundamentals)
        if not allowed:
            return _empty_frame()

        history = self.client.fetch_history(allowed, period=HISTORY_PERIOD, force_refresh=force_refresh)
        benchmark_close = self._benchmark_close(force_refresh)
        context = assess_market_context(benchmark_close, self.strategy)

        rows = []
        for ticker in allowed:
            row = self._evaluate_ticker(
                ticker, history.get(ticker), benchmark_close, context, fundamentals, universe, config
            )
            if row is not None:
                rows.append(row)
        if not rows:
            return _empty_frame()
        portfolio = assign_portfolio(pd.DataFrame(rows), self.portfolio)
        return portfolio.reindex(columns=list(RESULT_COLUMNS))

    def analyze(
        self,
        universe: UniverseResult,
        config: FilterConfig,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Return one row per ticker with setup/plan/confidence and no gating.

        Unlike :meth:`screen`, every ticker with computable features is included
        (even ``Avoid`` setups or low-confidence names); the ``Actionable``
        column flags those that would pass the screen gates. Used to drive the
        per-position analysis in the UI, where held names must always show a
        plan whether or not they are currently actionable.
        """
        if not universe.tickers:
            return _empty_analysis_frame()

        fundamentals = self.client.fetch_fundamentals(universe.tickers, force_refresh=force_refresh)
        allowed, _ = self.client.filter_allowed_exchanges(fundamentals)
        if not allowed:
            return _empty_analysis_frame()

        history = self.client.fetch_history(allowed, period=HISTORY_PERIOD, force_refresh=force_refresh)
        benchmark_close = self._benchmark_close(force_refresh)
        context = assess_market_context(benchmark_close, self.strategy)

        rows = []
        for ticker in allowed:
            analysis = self._compute_ticker(
                ticker, history.get(ticker), benchmark_close, fundamentals, universe
            )
            if analysis is None:
                continue
            rank = composite_rank(analysis.confidence, context)
            row = _result_row(
                ticker,
                analysis.company_name,
                analysis.fundamental,
                analysis.features,
                analysis.setup,
                analysis.plan,
                analysis.confidence,
                rank,
                context,
            )
            row['Actionable'] = self._passes_gates(analysis, config)
            rows.append(row)
        if not rows:
            return _empty_analysis_frame()
        return pd.DataFrame(rows).reindex(columns=list(ANALYSIS_COLUMNS))

    def _benchmark_close(self, force_refresh: bool) -> pd.Series:
        history = self.client.fetch_history([BENCHMARK_TICKER], period=HISTORY_PERIOD, force_refresh=force_refresh)
        benchmark = history.get(BENCHMARK_TICKER, pd.DataFrame())
        return benchmark.get('Close', pd.Series(dtype=float)).dropna()

    def backtest(
        self,
        universe: UniverseResult,
        params: BacktestParams,
        force_refresh: bool = False,
        max_symbols: int | None = None,
    ) -> list[Trade]:
        """Replay the live pipeline over historical bars for the universe.

        ``max_symbols`` caps how many symbols are simulated (the run is heavy);
        ``None`` backtests every allowed symbol.
        """
        if not universe.tickers:
            return []

        fundamentals = self.client.fetch_fundamentals(universe.tickers, force_refresh=force_refresh)
        allowed, _ = self.client.filter_allowed_exchanges(fundamentals)
        if max_symbols is not None:
            allowed = allowed[:max_symbols]
        if not allowed:
            return []

        history = self.client.fetch_history(allowed, period=HISTORY_PERIOD, force_refresh=force_refresh)
        benchmark_close = self._benchmark_close(force_refresh)
        return backtest_universe(history, benchmark_close, self.strategy, params)

    def _evaluate_ticker(
        self,
        ticker: str,
        df: pd.DataFrame | None,
        benchmark_close: pd.Series,
        context: MarketContext,
        fundamentals: dict[str, Fundamentals],
        universe: UniverseResult,
        config: FilterConfig,
    ) -> dict | None:
        """Return a result row for an actionable candidate, else ``None``."""
        analysis = self._compute_ticker(ticker, df, benchmark_close, fundamentals, universe)
        if analysis is None or not self._passes_gates(analysis, config):
            return None
        rank = composite_rank(analysis.confidence, context)
        return _result_row(
            ticker,
            analysis.company_name,
            analysis.fundamental,
            analysis.features,
            analysis.setup,
            analysis.plan,
            analysis.confidence,
            rank,
            context,
        )

    def _compute_ticker(
        self,
        ticker: str,
        df: pd.DataFrame | None,
        benchmark_close: pd.Series,
        fundamentals: dict[str, Fundamentals],
        universe: UniverseResult,
    ) -> _TickerAnalysis | None:
        """Compute features/setup/plan/confidence for a ticker (no gating).

        Returns ``None`` only when there is not enough data to compute features.
        """
        features = compute_features(df, benchmark_close, self.strategy)
        if features is None:
            return None
        setup = detect_setup(features, self.strategy)
        plan = build_trade_plan(features, setup, self.strategy)
        confidence = confidence_score(features, setup, plan, self.strategy)
        fundamental = fundamentals.get(ticker) or Fundamentals(ticker, None, None, None, None, None)
        company_name = fundamental.company_name or universe.companies.get(ticker, '')
        return _TickerAnalysis(features, setup, plan, confidence, fundamental, company_name)

    def _passes_gates(self, analysis: _TickerAnalysis, config: FilterConfig) -> bool:
        """Return whether an analysis clears the screen's actionability gates."""
        if analysis.features.avg_volume < config.min_avg_volume:
            return False
        if analysis.setup.setup_type == AVOID:
            return False
        if config.setups is not None and analysis.setup.setup_type not in config.setups:
            return False
        if analysis.plan.reward_risk is None or analysis.plan.reward_risk < config.min_reward_risk:
            return False
        if analysis.confidence < config.min_confidence:
            return False
        return True


def _result_row(
    ticker, company_name, fundamental, features, setup, plan, confidence, rank, context
) -> dict:
    return {
        'Ticker': ticker,
        'Company Name': company_name,
        'Setup': setup.setup_type,
        'Confidence': confidence,
        'Rank Score': rank,
        'Entry': plan.entry,
        'Stop': plan.stop,
        'Target': plan.target,
        'Risk %': plan.risk_pct,
        'Reward %': plan.reward_pct,
        'R/R': plan.reward_risk,
        'Reason': setup.reason,
        'Key Factors': '; '.join(setup.factors),
        'Risks': '; '.join(setup.risks),
        'Trend Score': features.trend_score,
        'RS Outperformance': features.rs_outperformance,
        'Rel Volume': features.rel_volume,
        'Market Cap': fundamental.market_cap,
        'PE Ratio': fundamental.pe_ratio,
        'Revenue Growth': fundamental.revenue_growth,
        'Price': features.price,
        'Market Context': context.label,
    }


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(RESULT_COLUMNS))


def _empty_analysis_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(ANALYSIS_COLUMNS))

