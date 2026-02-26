"""Integration test: finance trading agent workflow e2e."""
from __future__ import annotations

from typing import Any

import pytest

from agit import ExecutionEngine, RetryEngine


# ---------------------------------------------------------------------------
# Simulated finance domain helpers (no external deps)
# ---------------------------------------------------------------------------

RISK_LIMIT = 0.70  # 70% max risk score

MARKET_DATA: dict[str, dict[str, Any]] = {
    "AAPL": {"price": 182.50, "volatility": 0.25, "volume": 85_000_000},
    "TSLA": {"price": 248.00, "volatility": 0.65, "volume": 120_000_000},
    "MSFT": {"price": 415.00, "volatility": 0.18, "volume": 30_000_000},
    "GME":  {"price": 17.50, "volatility": 0.95, "volume": 5_000_000},
}


def fetch_market_data(state: dict[str, Any]) -> dict[str, Any]:
    """Step 1: Fetch market data for target ticker."""
    memory = state.get("memory", {})
    ticker = memory.get("ticker", "AAPL")
    data = MARKET_DATA.get(ticker, {"price": 0.0, "volatility": 0.5, "volume": 0})
    return {
        **state,
        "memory": {
            **memory,
            "market_data": data,
            "ticker": ticker,
            "data_fetched": True,
        },
    }


def calculate_risk_score(state: dict[str, Any]) -> dict[str, Any]:
    """Step 2: Calculate risk score from market data."""
    memory = state.get("memory", {})
    market_data = memory.get("market_data", {})
    volatility = market_data.get("volatility", 0.5)
    # Simple risk model: risk = volatility * position_size_factor
    position_size = memory.get("position_size", 10_000)
    max_position = memory.get("max_position", 100_000)
    size_factor = min(position_size / max_position, 1.0)
    risk_score = volatility * (0.5 + 0.5 * size_factor)
    return {
        **state,
        "memory": {
            **memory,
            "risk_score": risk_score,
            "risk_calculated": True,
        },
    }


def enforce_risk_limit(state: dict[str, Any]) -> dict[str, Any]:
    """Step 3: Enforce risk limit – raises if limit breached."""
    memory = state.get("memory", {})
    risk_score = memory.get("risk_score", 0.0)
    if risk_score > RISK_LIMIT:
        raise ValueError(
            f"Risk limit breached: score={risk_score:.3f} > limit={RISK_LIMIT}"
        )
    return {
        **state,
        "memory": {
            **memory,
            "risk_approved": True,
        },
    }


def execute_trade(state: dict[str, Any]) -> dict[str, Any]:
    """Step 4: Execute the trade."""
    memory = state.get("memory", {})
    ticker = memory.get("ticker", "AAPL")
    market_data = memory.get("market_data", {})
    position_size = memory.get("position_size", 10_000)
    price = market_data.get("price", 0.0)
    shares = int(position_size / price) if price else 0
    return {
        **state,
        "memory": {
            **memory,
            "trade": {
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "total": shares * price,
                "status": "executed",
            },
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def finance_engine() -> ExecutionEngine:
    return ExecutionEngine(":memory:", agent_id="finance-agent")


class TestTradingWorkflow:
    """Simulate trading workflow with agit versioning."""

    def test_full_trade_low_risk(self, finance_engine: ExecutionEngine) -> None:
        """MSFT trade should pass risk limits and execute."""
        state: dict[str, Any] = {
            "memory": {
                "ticker": "MSFT",
                "position_size": 10_000,
                "max_position": 100_000,
                "cumulative_cost": 0.0,
            },
            "world_state": {"market": "open"},
        }

        r1, h1 = finance_engine.execute(fetch_market_data, state, "fetch MSFT data")
        assert r1["memory"]["data_fetched"] is True

        r2, h2 = finance_engine.execute(calculate_risk_score, r1, "calc risk score")
        assert r2["memory"]["risk_score"] <= RISK_LIMIT

        r3, h3 = finance_engine.execute(enforce_risk_limit, r2, "enforce risk limit")
        assert r3["memory"]["risk_approved"] is True

        r4, h4 = finance_engine.execute(execute_trade, r3, "execute trade")
        assert r4["memory"]["trade"]["status"] == "executed"
        assert r4["memory"]["trade"]["shares"] > 0

        history = finance_engine.get_history(limit=20)
        assert len(history) >= 4

    def test_risk_limit_enforcement_blocks_high_risk_trade(
        self, finance_engine: ExecutionEngine
    ) -> None:
        """GME with high volatility should be blocked by risk limit."""
        state: dict[str, Any] = {
            "memory": {
                "ticker": "GME",
                "position_size": 80_000,
                "max_position": 100_000,
                "cumulative_cost": 0.0,
            },
            "world_state": {"market": "open"},
        }

        r1, h1 = finance_engine.execute(fetch_market_data, state, "fetch GME data")
        r2, h2 = finance_engine.execute(calculate_risk_score, r1, "calc risk score")
        assert r2["memory"]["risk_score"] > RISK_LIMIT

        with pytest.raises(ValueError, match="Risk limit breached"):
            finance_engine.execute(enforce_risk_limit, r2, "enforce risk limit - should fail")

        # Verify error commit recorded
        history = finance_engine.get_history(limit=20)
        messages = [c["message"] for c in history]
        assert any("error:" in m for m in messages)

    def test_audit_trail_for_compliance(self, finance_engine: ExecutionEngine) -> None:
        """All trading steps must appear in the audit trail."""
        state: dict[str, Any] = {
            "memory": {
                "ticker": "AAPL",
                "position_size": 5_000,
                "max_position": 100_000,
                "cumulative_cost": 0.0,
            },
            "world_state": {},
        }

        r1, _ = finance_engine.execute(fetch_market_data, state, "fetch data")
        r2, _ = finance_engine.execute(calculate_risk_score, r1, "calc risk")
        r3, _ = finance_engine.execute(enforce_risk_limit, r2, "enforce limit")
        r4, _ = finance_engine.execute(execute_trade, r3, "execute")

        audit = finance_engine.audit_log(limit=50)
        assert len(audit) >= 4
        commit_entries = [e for e in audit if e["action"] == "commit"]
        assert len(commit_entries) >= 4

    def test_branch_per_trade_isolation(self, finance_engine: ExecutionEngine) -> None:
        """Each trade uses an isolated branch."""
        base_state: dict[str, Any] = {
            "memory": {"cumulative_cost": 0.0, "portfolio": {}},
            "world_state": {"market": "open"},
        }
        h_base = finance_engine.commit_state(base_state, "portfolio start", "checkpoint")

        for ticker in ["AAPL", "MSFT"]:
            branch = f"trade/{ticker.lower()}"
            finance_engine.branch(branch, from_ref=h_base)
            finance_engine.checkout(branch)
            trade_state = {
                **base_state,
                "memory": {**base_state["memory"], "ticker": ticker, "position_size": 5_000, "max_position": 100_000},
            }
            r1, _ = finance_engine.execute(fetch_market_data, trade_state, f"fetch {ticker}")
            finance_engine.checkout("main")

        branches = finance_engine.list_branches()
        assert "trade/aapl" in branches
        assert "trade/msft" in branches

    def test_rollback_on_risk_breach(self, finance_engine: ExecutionEngine) -> None:
        """Can rollback to pre-risk-check state after a breach."""
        state: dict[str, Any] = {
            "memory": {
                "ticker": "GME",
                "position_size": 90_000,
                "max_position": 100_000,
                "cumulative_cost": 0.0,
            },
            "world_state": {},
        }
        h_safe = finance_engine.commit_state(state, "safe baseline", "checkpoint")
        r1, h1 = finance_engine.execute(fetch_market_data, state, "fetch data")
        r2, h2 = finance_engine.execute(calculate_risk_score, r1, "calc risk")

        with pytest.raises(ValueError):
            finance_engine.execute(enforce_risk_limit, r2, "enforce limit - fail")

        # Rollback to safe baseline
        restored = finance_engine.revert(h_safe)
        assert restored["memory"]["ticker"] == "GME"
        assert "risk_score" not in restored.get("memory", {})

    def test_retry_on_transient_market_data_failure(
        self, finance_engine: ExecutionEngine
    ) -> None:
        """RetryEngine retries on transient market data fetch failures."""
        call_count = {"n": 0}

        def flaky_fetch(state: dict[str, Any]) -> dict[str, Any]:
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ConnectionError("market data API timeout")
            return fetch_market_data(state)

        initial: dict[str, Any] = {
            "memory": {"ticker": "AAPL", "position_size": 5_000, "max_position": 100_000, "cumulative_cost": 0.0},
            "world_state": {},
        }
        retry_eng = RetryEngine(finance_engine, max_retries=3, base_delay=0.0)
        result, history = retry_eng.execute_with_retry(flaky_fetch, initial, "fetch market data")
        assert history.succeeded
        assert result["memory"]["data_fetched"] is True
