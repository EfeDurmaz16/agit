"""Streamlit audit dashboard – standalone app with sidebar, filters, search, and timeline."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta
from typing import Any


def render_audit_dashboard(logs: list[dict[str, Any]]) -> None:
    """Render an interactive audit dashboard in a Streamlit app."""
    try:
        import streamlit as st
    except ImportError as exc:
        raise ImportError("streamlit is required: pip install agit[ui]") from exc

    try:
        import plotly.express as px
        import plotly.graph_objects as go
        _PLOTLY = True
    except ImportError:
        _PLOTLY = False

    st.title("agit Audit Dashboard")

    if not logs:
        st.warning("No audit log entries to display.")
        return

    # ------------------------------------------------------------------
    # Metrics row
    # ------------------------------------------------------------------
    total = len(logs)
    agents = len({e.get("agent_id", "") for e in logs})
    actions = len({e.get("action", "") for e in logs})
    commits = sum(1 for e in logs if e.get("commit_hash"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Events", total)
    c2.metric("Agents", agents)
    c3.metric("Unique Actions", actions)
    c4.metric("Commits", commits)

    st.divider()

    # ------------------------------------------------------------------
    # Sidebar filters
    # ------------------------------------------------------------------
    with st.sidebar:
        st.header("Filters")

        all_agents = sorted({e.get("agent_id", "unknown") for e in logs})
        selected_agents = st.multiselect("Agent ID", all_agents, default=all_agents)

        all_actions = sorted({e.get("action", "unknown") for e in logs})
        selected_actions = st.multiselect("Action", all_actions, default=all_actions)

        # Date range filter
        st.subheader("Date Range")
        timestamps = []
        for e in logs:
            ts = e.get("timestamp", "")
            if ts:
                try:
                    timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                except (ValueError, TypeError):
                    pass

        if timestamps:
            min_date = min(timestamps).date()
            max_date = max(timestamps).date()
            date_range = st.date_input(
                "Date range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
            )
        else:
            date_range = None

        # Search
        st.subheader("Search")
        search_query = st.text_input("Search messages", "")

    # Apply filters
    filtered = [
        e for e in logs
        if e.get("agent_id", "unknown") in selected_agents
        and e.get("action", "unknown") in selected_actions
    ]

    # Apply date filter
    if date_range and len(date_range) == 2:
        start_date, end_date = date_range
        filtered = [
            e for e in filtered
            if _in_date_range(e.get("timestamp", ""), start_date, end_date)
        ]

    # Apply search
    if search_query:
        query_lower = search_query.lower()
        filtered = [
            e for e in filtered
            if query_lower in e.get("message", "").lower()
            or query_lower in e.get("commit_hash", "").lower()
            or query_lower in e.get("action", "").lower()
        ]

    st.caption(f"Showing {len(filtered)} of {total} entries")

    # ------------------------------------------------------------------
    # Timeline chart
    # ------------------------------------------------------------------
    st.subheader("Event Timeline")
    if _PLOTLY and filtered:
        try:
            import pandas as pd
            df = pd.DataFrame(filtered)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
                df = df.dropna(subset=["timestamp"])
                df = df.sort_values("timestamp")
                fig = px.scatter(
                    df, x="timestamp", y="action", color="agent_id",
                    hover_data=["message", "commit_hash"],
                    title="Audit Events Over Time", height=400,
                )
                fig.update_traces(marker={"size": 10})
                st.plotly_chart(fig, use_container_width=True)
        except Exception as exc:
            st.warning(f"Could not render timeline: {exc}")
    else:
        st.info("Install plotly and pandas for charts: pip install agit[ui] pandas")

    # ------------------------------------------------------------------
    # Action breakdown
    # ------------------------------------------------------------------
    if _PLOTLY and filtered:
        st.subheader("Action Breakdown")
        action_counts: dict[str, int] = {}
        for e in filtered:
            a = e.get("action", "unknown")
            action_counts[a] = action_counts.get(a, 0) + 1
        fig2 = go.Figure(data=[go.Pie(
            labels=list(action_counts.keys()),
            values=list(action_counts.values()),
        )])
        fig2.update_layout(title="Events by Action Type", height=350)
        st.plotly_chart(fig2, use_container_width=True)

    # ------------------------------------------------------------------
    # Log table
    # ------------------------------------------------------------------
    st.subheader("Audit Log Entries")
    st.dataframe(
        [
            {
                "Timestamp": e.get("timestamp", ""),
                "Agent": e.get("agent_id", ""),
                "Action": e.get("action", ""),
                "Message": e.get("message", ""),
                "Commit": (e.get("commit_hash") or "")[:12],
            }
            for e in filtered
        ],
        use_container_width=True,
    )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    st.subheader("Export")
    col1, col2 = st.columns(2)
    with col1:
        json_bytes = json.dumps(filtered, indent=2, default=str).encode()
        st.download_button("Download JSON", json_bytes, "agit_audit.json", "application/json")
    with col2:
        csv_buf = io.StringIO()
        if filtered:
            writer = csv.DictWriter(csv_buf, fieldnames=list(filtered[0].keys()), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(filtered)
        st.download_button("Download CSV", csv_buf.getvalue().encode(), "agit_audit.csv", "text/csv")


def _in_date_range(ts_str: str, start_date: Any, end_date: Any) -> bool:
    """Check if a timestamp string falls within a date range."""
    if not ts_str:
        return True
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).date()
        return start_date <= ts <= end_date
    except (ValueError, TypeError):
        return True


# ------------------------------------------------------------------
# Standalone app entry point
# ------------------------------------------------------------------
def _run_standalone() -> None:
    """Run as a standalone Streamlit app with repo path input."""
    try:
        import streamlit as st
    except ImportError:
        print("streamlit required: pip install agit[ui]")
        return

    from agit.engine.executor import ExecutionEngine

    st.set_page_config(page_title="agit Audit Dashboard", layout="wide")

    with st.sidebar:
        st.header("Repository")
        repo_path = st.text_input("Repo path", value=".")
        agent_id = st.text_input("Agent ID", value="cli")
        limit = st.slider("Max entries", 10, 500, 100)

    try:
        engine = ExecutionEngine(repo_path=repo_path, agent_id=agent_id)
        logs = engine.audit_log(limit)
        render_audit_dashboard(logs)
    except Exception as exc:
        st.error(f"Failed to load repository: {exc}")
        st.info("Make sure the repo path points to an initialized agit repository.")


if __name__ == "__main__":
    _run_standalone()
