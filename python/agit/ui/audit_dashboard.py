"""Streamlit audit dashboard – timeline visualisation and compliance export."""
from __future__ import annotations

import csv
import io
import json
from typing import Any


def render_audit_dashboard(logs: list[dict[str, Any]]) -> None:
    """Render an interactive audit dashboard in a Streamlit app.

    Parameters
    ----------
    logs:
        List of audit log entry dicts, each containing at minimum:
        ``timestamp``, ``agent_id``, ``action``, ``message``, ``commit_hash``.

    Raises ``ImportError`` if ``streamlit`` or ``plotly`` are not installed.
    """
    try:
        import streamlit as st  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "streamlit is required. Install with: pip install agit[ui]"
        ) from exc

    try:
        import plotly.express as px  # type: ignore[import]
        import plotly.graph_objects as go  # type: ignore[import]
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

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Events", total)
    c2.metric("Agents", agents)
    c3.metric("Unique Actions", actions)

    st.divider()

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------
    with st.sidebar:
        st.header("Filters")
        all_agents = sorted({e.get("agent_id", "unknown") for e in logs})
        selected_agents = st.multiselect("Agent ID", all_agents, default=all_agents)

        all_actions = sorted({e.get("action", "unknown") for e in logs})
        selected_actions = st.multiselect("Action", all_actions, default=all_actions)

    filtered = [
        e for e in logs
        if e.get("agent_id", "unknown") in selected_agents
        and e.get("action", "unknown") in selected_actions
    ]

    # ------------------------------------------------------------------
    # Timeline chart
    # ------------------------------------------------------------------
    st.subheader("Event Timeline")

    if _PLOTLY and filtered:
        try:
            import pandas as pd  # type: ignore[import]

            df = pd.DataFrame(filtered)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
                df = df.dropna(subset=["timestamp"])
                df = df.sort_values("timestamp")

                fig = px.scatter(
                    df,
                    x="timestamp",
                    y="action",
                    color="agent_id",
                    hover_data=["message", "commit_hash"],
                    title="Audit Events Over Time",
                    height=400,
                )
                fig.update_traces(marker={"size": 10})
                st.plotly_chart(fig, use_container_width=True)
        except Exception as exc:
            st.warning(f"Could not render timeline chart: {exc}")
    else:
        st.info("Install plotly and pandas for timeline visualisation: pip install agit[ui] pandas")

    # ------------------------------------------------------------------
    # Action breakdown pie chart
    # ------------------------------------------------------------------
    if _PLOTLY and filtered:
        st.subheader("Action Breakdown")
        action_counts: dict[str, int] = {}
        for e in filtered:
            action_counts[e.get("action", "unknown")] = action_counts.get(e.get("action", "unknown"), 0) + 1

        fig2 = go.Figure(
            data=[go.Pie(labels=list(action_counts.keys()), values=list(action_counts.values()))]
        )
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
    # Compliance export
    # ------------------------------------------------------------------
    st.subheader("Export")
    export_col1, export_col2 = st.columns(2)

    with export_col1:
        json_bytes = json.dumps(filtered, indent=2, default=str).encode()
        st.download_button(
            label="Download JSON",
            data=json_bytes,
            file_name="agit_audit_log.json",
            mime="application/json",
        )

    with export_col2:
        csv_buf = io.StringIO()
        if filtered:
            fieldnames = list(filtered[0].keys())
            writer = csv.DictWriter(csv_buf, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(filtered)
        st.download_button(
            label="Download CSV",
            data=csv_buf.getvalue().encode(),
            file_name="agit_audit_log.csv",
            mime="text/csv",
        )
