"""State replay UI – time-travel through agent state history."""
from __future__ import annotations

from typing import Any


def render_state_replay(engine: Any) -> None:
    """Render a state replay interface with timeline slider.

    Parameters
    ----------
    engine:
        An initialized ExecutionEngine instance.
    """
    try:
        import streamlit as st
    except ImportError as exc:
        raise ImportError("streamlit is required: pip install agit[ui]") from exc

    import json

    st.title("agit State Replay")

    # Get commit history
    commits = engine.get_history(100)
    if not commits:
        st.warning("No commits to replay.")
        return

    # Reverse to chronological order (oldest first)
    commits = list(reversed(commits))

    st.caption(f"{len(commits)} commits available")

    # Timeline slider
    step = st.slider(
        "Step through history",
        min_value=0,
        max_value=len(commits) - 1,
        value=len(commits) - 1,
        format="Step %d",
    )

    current_commit = commits[step]
    commit_hash = current_commit.get("hash", "")

    # Commit info
    col1, col2, col3 = st.columns(3)
    col1.metric("Step", f"{step + 1}/{len(commits)}")
    col2.metric("Action", current_commit.get("action_type", ""))
    col3.metric("Hash", commit_hash[:12])

    st.text(f"Message: {current_commit.get('message', '')}")
    st.text(f"Author: {current_commit.get('author', '')}  |  Time: {current_commit.get('timestamp', '')}")

    st.divider()

    # Try to get state at this commit
    try:
        state = engine.checkout(commit_hash)
        engine.checkout(engine.current_branch() or "main")  # restore position

        st.subheader("State at this commit")
        st.json(state)
    except Exception as exc:
        st.warning(f"Could not retrieve state: {exc}")

    # Show diff with previous
    if step > 0:
        prev_hash = commits[step - 1].get("hash", "")
        if prev_hash and commit_hash:
            st.subheader("Changes from previous step")
            try:
                diff = engine.diff(prev_hash, commit_hash)
                entries = diff.get("entries", [])
                if entries:
                    for entry in entries:
                        ct = entry.get("change_type", "")
                        path = entry.get("path", "")
                        old = json.dumps(entry.get("old_value"), default=str)
                        new = json.dumps(entry.get("new_value"), default=str)
                        if ct == "added":
                            st.markdown(f"**+** `{path}` = `{new}`")
                        elif ct == "removed":
                            st.markdown(f"**-** `{path}` = ~~`{old}`~~")
                        else:
                            st.markdown(f"**~** `{path}`: `{old}` → `{new}`")
                else:
                    st.info("No changes in this step.")
            except Exception:
                st.info("Diff not available for this step.")

    # Playback controls
    st.divider()
    st.subheader("Branch Visualization")
    branches = engine.list_branches()
    current = engine.current_branch()
    for bname, bhash in sorted(branches.items()):
        marker = " (current)" if bname == current else ""
        st.text(f"  {'*' if bname == current else ' '} {bname}: {bhash[:12]}{marker}")


# Standalone entry
if __name__ == "__main__":
    try:
        import streamlit as st
        from agit.engine.executor import ExecutionEngine

        st.set_page_config(page_title="agit State Replay", layout="wide")

        with st.sidebar:
            repo_path = st.text_input("Repo path", ".")
            agent_id = st.text_input("Agent ID", "cli")

        engine = ExecutionEngine(repo_path=repo_path, agent_id=agent_id)
        render_state_replay(engine)
    except ImportError:
        print("streamlit required: pip install agit[ui]")
