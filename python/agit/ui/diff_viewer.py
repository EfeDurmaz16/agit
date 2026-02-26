"""Streamlit diff viewer – side-by-side JSON diff display with colour coding."""
from __future__ import annotations

import json
from typing import Any


def render_diff_viewer(diff: dict[str, Any]) -> None:
    """Render a side-by-side diff view in a Streamlit app.

    Parameters
    ----------
    diff:
        A diff dict as returned by :meth:`ExecutionEngine.diff`, containing
        ``base_hash``, ``target_hash``, and ``entries``.

    The function is importable even without Streamlit installed; it will raise
    an ``ImportError`` only when actually called in an environment without
    Streamlit.
    """
    try:
        import streamlit as st  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "streamlit is required for render_diff_viewer. "
            "Install it with: pip install agit[ui]"
        ) from exc

    base_hash: str = diff.get("base_hash", "unknown")
    target_hash: str = diff.get("target_hash", "unknown")
    entries: list[dict[str, Any]] = diff.get("entries", [])

    st.subheader("Diff Viewer")
    st.caption(f"**Base:** `{base_hash[:12]}` → **Target:** `{target_hash[:12]}`")

    if not entries:
        st.info("No differences between the two commits.")
        return

    # Summary metrics
    added = sum(1 for e in entries if e.get("change_type") == "added")
    removed = sum(1 for e in entries if e.get("change_type") == "removed")
    changed = sum(1 for e in entries if e.get("change_type") == "changed")

    col1, col2, col3 = st.columns(3)
    col1.metric("Added", added, delta=f"+{added}", delta_color="normal")
    col2.metric("Removed", removed, delta=f"-{removed}", delta_color="inverse")
    col3.metric("Changed", changed)

    st.divider()

    # Side-by-side table
    left_col, right_col = st.columns(2)
    left_col.markdown("### Base")
    right_col.markdown("### Target")

    _CHANGE_COLOURS = {
        "added": "#1a7a1a",    # green background
        "removed": "#7a1a1a",  # red background
        "changed": "#7a5a00",  # amber background
    }

    for entry in entries:
        path: str = entry.get("path", "")
        ct: str = entry.get("change_type", "")
        old_val = entry.get("old_value")
        new_val = entry.get("new_value")

        colour = _CHANGE_COLOURS.get(ct, "#333333")
        label_style = f"background-color:{colour};padding:2px 6px;border-radius:4px;color:#fff;font-size:0.75em;"
        badge = f'<span style="{label_style}">{ct.upper()}</span>'

        with left_col:
            st.markdown(f"**`{path}`** {badge}", unsafe_allow_html=True)
            if ct != "added":
                st.code(
                    json.dumps(old_val, indent=2, default=str) if old_val is not None else "—",
                    language="json",
                )
            else:
                st.markdown("*(not present)*")

        with right_col:
            st.markdown(f"**`{path}`** {badge}", unsafe_allow_html=True)
            if ct != "removed":
                st.code(
                    json.dumps(new_val, indent=2, default=str) if new_val is not None else "—",
                    language="json",
                )
            else:
                st.markdown("*(removed)*")

    st.divider()
    with st.expander("Raw diff JSON"):
        st.json(diff)
