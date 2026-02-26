"""Finance trading bot demo with agit versioning.

Demonstrates:
- Branch-per-trade isolation
- Risk limit enforcement with rollback on breach
- Retry on transient market data failures
- Full audit trail for compliance

Run:
    python examples/finance_trade.py
"""
from __future__ import annotations

import json
import random
import tempfile
from typing import Any

from agit.engine.executor import ExecutionEngine
from agit.engine.retry import RetryEngine


# ---------------------------------------------------------------------------
# Domain data
# ---------------------------------------------------------------------------

RISK_LIMIT = 0.65

MARKET: dict[str, dict[str, Any]] = {
    "AAPL": {"price": 182.50, "volume": 85_000_000, "volatility": 0.22, "sector": "tech"},
    "MSFT": {"price": 415.00, "volume": 30_000_000, "volatility": 0.18, "sector": "tech"},
    "TSLA": {"price": 248.00, "volume": 120_000_000,"volatility": 0.60, "sector": "auto"},
    "GME":  {"price": 17.50,  "volume": 5_000_000,  "volatility": 0.92, "sector": "retail"},
    "NVDA": {"price": 870.00, "volume": 40_000_000, "volatility": 0.35, "sector": "semi"},
}


# ---------------------------------------------------------------------------
# Agent action functions
# ---------------------------------------------------------------------------


def fetch_market_data(state: dict[str, Any]) -> dict[str, Any]:
    """Step 1: Fetch real-time market data."""
    symbol = state["memory"].get("symbol", "AAPL")
    data = MARKET.get(symbol, {"price": 0.0, "volume": 0, "volatility": 0.5, "sector": "unknown"})
    state["memory"]["market"] = {**data, "symbol": symbol}
    state["world_state"]["step"] = "market_data_fetched"
    print(f"  [1] Market data: {symbol} ${data['price']} vol={data['volatility']:.2f}")
    return state


def compute_risk_score(state: dict[str, Any]) -> dict[str, Any]:
    """Step 2: Compute risk score using volatility and position size."""
    market = state["memory"]["market"]
    vol = market["volatility"]
    position = state["memory"].get("position_usd", 10_000)
    cap = state["memory"].get("max_position_usd", 100_000)
    size_factor = min(position / cap, 1.0)
    risk = round(vol * (0.4 + 0.6 * size_factor), 4)

    state["memory"]["risk"] = {
        "score": risk,
        "level": "high" if risk > 0.5 else "medium" if risk > 0.3 else "low",
        "limit": RISK_LIMIT,
        "within_limit": risk <= RISK_LIMIT,
    }
    state["world_state"]["step"] = "risk_scored"
    print(f"  [2] Risk score: {risk:.4f}  (limit={RISK_LIMIT}, {'OK' if risk <= RISK_LIMIT else 'BREACH'})")
    return state


def enforce_risk_limit(state: dict[str, Any]) -> dict[str, Any]:
    """Step 3: Enforce risk limit – raise if breached."""
    risk = state["memory"]["risk"]
    if not risk["within_limit"]:
        raise ValueError(
            f"RISK BREACH: score={risk['score']:.4f} exceeds limit={RISK_LIMIT}"
        )
    state["memory"]["risk_approved"] = True
    state["world_state"]["step"] = "risk_approved"
    print("  [3] Risk approved")
    return state


def execute_trade(state: dict[str, Any]) -> dict[str, Any]:
    """Step 4: Execute the trade."""
    market = state["memory"]["market"]
    position = state["memory"].get("position_usd", 10_000)
    price = market["price"]
    shares = int(position / price) if price else 0
    commission = round(shares * price * 0.001, 2)
    trade = {
        "symbol": market["symbol"],
        "action": "BUY",
        "shares": shares,
        "price": price,
        "total_usd": round(shares * price, 2),
        "commission": commission,
        "risk_level": state["memory"]["risk"]["level"],
        "status": "executed",
    }
    state["memory"]["trade"] = trade
    state["world_state"]["step"] = "trade_executed"
    print(f"  [4] Executed: BUY {shares} {market['symbol']} @ ${price} = ${trade['total_usd']:,.2f}")
    return state


# ---------------------------------------------------------------------------
# Demo orchestration
# ---------------------------------------------------------------------------


def run_trade_session(symbols: list[str], position_usd: int = 10_000) -> None:
    print(f"\n{'='*60}")
    print(f"  Finance Agent: Trading Session  ({', '.join(symbols)})")
    print(f"{'='*60}\n")

    with tempfile.TemporaryDirectory() as tmp:
        engine = ExecutionEngine(repo_path=tmp, agent_id="trading-bot")

        # Establish session baseline
        portfolio: dict[str, Any] = {
            "memory": {"portfolio": {}, "cumulative_cost": 0.0},
            "world_state": {"session": "2026-02-26", "market": "open"},
        }
        h_base = engine.commit_state(portfolio, "session start", "checkpoint")
        print(f"  Session baseline: {h_base[:12]}")

        results: list[dict[str, Any]] = []

        for symbol in symbols:
            print(f"\n  --- {symbol} ---")
            branch = f"trade/{symbol.lower()}"
            engine.branch(branch, from_ref=h_base)
            engine.checkout(branch)

            state: dict[str, Any] = {
                "memory": {
                    "symbol": symbol,
                    "position_usd": position_usd,
                    "max_position_usd": 100_000,
                    "cumulative_cost": 0.0,
                },
                "world_state": {"market": "open"},
            }

            # Retry wrapper for transient fetch failures
            call_count: dict[str, int] = {"n": 0}

            def maybe_flaky_fetch(s: dict[str, Any], sym: str = symbol) -> dict[str, Any]:
                call_count["n"] += 1
                if call_count["n"] == 1 and random.random() < 0.25:
                    raise ConnectionError(f"market API timeout for {sym}")
                return fetch_market_data(s)

            retry_eng = RetryEngine(engine, max_retries=2, base_delay=0.0)
            try:
                state, fetch_hist = retry_eng.execute_with_retry(
                    maybe_flaky_fetch, state, f"fetch {symbol}"
                )
                if fetch_hist.total_attempts > 1:
                    print(f"    (recovered after {fetch_hist.total_attempts} fetch attempts)")

                state, _ = engine.execute(compute_risk_score, state, "compute risk")
                state, _ = engine.execute(enforce_risk_limit, state, "enforce risk limit")
                state, _ = engine.execute(execute_trade, state, "execute trade")
                results.append({"symbol": symbol, "trade": state["memory"]["trade"]})

                # Merge successful trade branch into main
                engine.checkout("main")
                try:
                    engine.merge(branch, strategy="theirs")
                except Exception:
                    pass
            except ValueError as exc:
                print(f"    BLOCKED: {exc}")
                results.append({"symbol": symbol, "trade": None, "blocked": str(exc)})
                engine.checkout("main")

        # Summary
        print(f"\n  {'='*50}")
        print("  Trade Summary:")
        for r in results:
            if r.get("trade"):
                t = r["trade"]
                print(f"    {r['symbol']:6}  BUY {t['shares']:4} shares  ${t['total_usd']:>10,.2f}  [{t['risk_level']}]")
            else:
                print(f"    {r['symbol']:6}  BLOCKED – {r.get('blocked','')[:40]}")

        # Compliance audit
        print("\n  Compliance Audit Trail (last 15 entries):")
        for entry in engine.audit_log(limit=15):
            print(f"    {entry['timestamp']}  {entry['action']:8}  {entry['message'][:50]}")

        print(f"\n{'='*60}\n")


def main() -> None:
    random.seed(42)
    run_trade_session(["AAPL", "MSFT", "TSLA", "GME", "NVDA"], position_usd=20_000)


if __name__ == "__main__":
    main()
