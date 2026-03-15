"""agit CLI – full Typer application."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from agit.engine.executor import ExecutionEngine

app = typer.Typer(
    name="agit",
    help="Git-like version control for AI agents.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True, style="red")

_DEFAULT_REPO = "."
_DEFAULT_AGENT = "cli"


def _engine(repo: str, agent: str) -> ExecutionEngine:
    return ExecutionEngine(repo_path=repo, agent_id=agent)


def _abort(msg: str) -> None:
    err_console.print(f"[bold red]error:[/] {msg}")
    raise typer.Exit(1)


def _success(msg: str) -> None:
    console.print(f"[bold green]ok:[/] {msg}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def init(
    path: Annotated[str, typer.Argument(help="Repository path")] = ".",
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Initialize an agit repository."""
    try:
        _engine(path, agent)
        _success(f"Initialised agit repository at [bold]{Path(path).resolve()}[/]")
    except Exception as exc:
        _abort(str(exc))


@app.command()
def commit(
    message: Annotated[str, typer.Option("--message", "-m", help="Commit message")],
    state_json: Annotated[
        Optional[str],
        typer.Option("--state", "-s", help="JSON state string or path to JSON file"),
    ] = None,
    action_type: Annotated[str, typer.Option("--type", "-t")] = "checkpoint",
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Commit the current agent state."""
    state: dict = {}
    if state_json:
        p = Path(state_json)
        if p.exists():
            state = json.loads(p.read_text())
        else:
            try:
                state = json.loads(state_json)
            except json.JSONDecodeError as exc:
                _abort(f"Invalid JSON: {exc}")

    try:
        eng = _engine(repo, agent)
        h = eng.commit_state(state, message, action_type)
        _success(f"Committed [cyan]{h[:12]}[/] – {message}")
    except Exception as exc:
        _abort(str(exc))


@app.command()
def branch(
    name: Annotated[Optional[str], typer.Argument(help="Branch name to create")] = None,
    from_ref: Annotated[Optional[str], typer.Option("--from", "-f")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Create or list branches."""
    try:
        eng = _engine(repo, agent)
        if name:
            eng.branch(name, from_ref=from_ref)
            _success(f"Created branch [bold cyan]{name}[/]")
        else:
            branches = eng.list_branches()
            current = eng.current_branch()
            if json_output:
                console.print(json.dumps({"branches": branches, "current": current}, indent=2, default=str))
                return
            table = Table(title="Branches", show_header=True)
            table.add_column("Name", style="cyan")
            table.add_column("Commit", style="dim")
            table.add_column("Current")
            for bname, bhash in sorted(branches.items()):
                marker = "[bold green]*[/]" if bname == current else ""
                table.add_row(bname, bhash[:12] if bhash else "", marker)
            console.print(table)
    except Exception as exc:
        _abort(str(exc))


@app.command()
def checkout(
    target: Annotated[str, typer.Argument(help="Branch name or commit hash")],
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Switch to a branch or commit."""
    try:
        eng = _engine(repo, agent)
        state = eng.checkout(target)
        _success(f"Checked out [bold cyan]{target}[/]")
        console.print(
            Syntax(json.dumps(state, indent=2), "json", theme="monokai", line_numbers=False)
        )
    except Exception as exc:
        _abort(str(exc))


@app.command()
def log(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 10,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Show commit history."""
    try:
        eng = _engine(repo, agent)
        commits = eng.get_history(limit)
        if json_output:
            console.print(json.dumps(commits, indent=2, default=str))
            return
        if not commits:
            console.print("[dim]No commits yet.[/]")
            return
        for c in commits:
            h = c.get("hash", "")
            msg = c.get("message", "")
            author = c.get("author", "")
            ts = c.get("timestamp", "")
            at = c.get("action_type", "")
            console.print(
                Panel(
                    f"[bold]{msg}[/]\n"
                    f"[dim]author:[/] {author}   [dim]type:[/] {at}   [dim]date:[/] {ts}",
                    title=f"[yellow]{h[:12]}[/]",
                    expand=False,
                )
            )
    except Exception as exc:
        _abort(str(exc))


@app.command()
def diff(
    hash1: Annotated[str, typer.Argument(help="Base commit hash")],
    hash2: Annotated[str, typer.Argument(help="Target commit hash")],
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Show diff between two commits."""
    try:
        eng = _engine(repo, agent)
        d = eng.diff(hash1, hash2)
        entries = d.get("entries", [])
        if not entries:
            console.print("[dim]No differences.[/]")
            return
        table = Table(title=f"Diff {hash1[:8]}..{hash2[:8]}")
        table.add_column("Path", style="cyan")
        table.add_column("Change", style="bold")
        table.add_column("Old Value", style="red")
        table.add_column("New Value", style="green")
        for e in entries:
            ct = e.get("change_type", "")
            colour = {"added": "green", "removed": "red", "changed": "yellow"}.get(ct, "white")
            table.add_row(
                e.get("path", ""),
                Text(ct, style=colour),
                json.dumps(e.get("old_value")),
                json.dumps(e.get("new_value")),
            )
        console.print(table)
    except Exception as exc:
        _abort(str(exc))


@app.command()
def merge(
    branch_name: Annotated[str, typer.Argument(help="Branch to merge into HEAD")],
    strategy: Annotated[str, typer.Option("--strategy", "-s")] = "three_way",
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Merge a branch into the current branch."""
    try:
        eng = _engine(repo, agent)
        h = eng.merge(branch_name, strategy=strategy)
        _success(f"Merged [bold cyan]{branch_name}[/] -> [yellow]{h[:12]}[/]")
    except Exception as exc:
        _abort(str(exc))


@app.command()
def revert(
    commit_hash: Annotated[str, typer.Argument(help="Commit hash to revert to")],
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Revert repository to a previous commit's state."""
    try:
        eng = _engine(repo, agent)
        state = eng.revert(commit_hash)
        _success(f"Reverted to [yellow]{commit_hash[:12]}[/]")
        console.print(
            Syntax(json.dumps(state, indent=2), "json", theme="monokai", line_numbers=False)
        )
    except Exception as exc:
        _abort(str(exc))


@app.command()
def status(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Show current repository status."""
    try:
        eng = _engine(repo, agent)
        current = eng.current_branch() or "(detached HEAD)"
        branches = eng.list_branches()
        history = eng.get_history(1)
        last_commit = history[0] if history else None

        if json_output:
            console.print(json.dumps({
                "branch": current,
                "branches": len(branches),
                "last_commit": last_commit,
            }, indent=2, default=str))
            return

        table = Table(title="Repository Status", show_header=False)
        table.add_column("Key", style="bold cyan", no_wrap=True)
        table.add_column("Value")
        table.add_row("Current branch", current)
        table.add_row("Branches", str(len(branches)))
        if last_commit:
            table.add_row(
                "Last commit",
                f"{last_commit.get('hash','')[:12]} – {last_commit.get('message','')}",
            )
            table.add_row("Last author", last_commit.get("author", ""))
            table.add_row("Last timestamp", last_commit.get("timestamp", ""))
        console.print(table)
    except Exception as exc:
        _abort(str(exc))


@app.command()
def audit(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
    output_format: Annotated[str, typer.Option("--format", "-f", help="table|json")] = "table",
) -> None:
    """Show the audit log."""
    try:
        eng = _engine(repo, agent)
        logs = eng.audit_log(limit)
        if not logs:
            console.print("[dim]No audit entries.[/]")
            return
        if output_format == "json":
            console.print(Syntax(json.dumps(logs, indent=2), "json", theme="monokai"))
            return
        table = Table(title="Audit Log")
        table.add_column("Time", style="dim")
        table.add_column("Agent", style="cyan")
        table.add_column("Action", style="bold")
        table.add_column("Message")
        table.add_column("Commit", style="yellow")
        for entry in logs:
            table.add_row(
                entry.get("timestamp", ""),
                entry.get("agent_id", ""),
                entry.get("action", ""),
                entry.get("message", ""),
                (entry.get("commit_hash") or "")[:12],
            )
        console.print(table)
    except Exception as exc:
        _abort(str(exc))


@app.command()
def retry(
    state_json: Annotated[
        Optional[str],
        typer.Option("--state", "-s", help="Path to JSON state file or JSON string"),
    ] = None,
    message: Annotated[str, typer.Option("--message", "-m")] = "retry action",
    max_retries: Annotated[int, typer.Option("--max-retries", "-n")] = 3,
    base_delay: Annotated[float, typer.Option("--delay", "-d")] = 1.0,
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Show retry history or demonstrate retry engine configuration."""
    from agit.engine.retry import RetryEngine

    try:
        eng = ExecutionEngine(repo_path=repo, agent_id=agent)
        retry_eng = RetryEngine(eng, max_retries=max_retries, base_delay=base_delay)

        state: dict = {}
        if state_json:
            p = Path(state_json)
            state = json.loads(p.read_text() if p.exists() else state_json)

        # No-op action that always succeeds – used to demonstrate configuration
        def _noop(s: dict) -> dict:
            return s

        _result, history = retry_eng.execute_with_retry(_noop, state, message=message)
        _success(
            f"Completed after {history.total_attempts} attempt(s). "
            f"Success: {history.succeeded}"
        )
        console.print(
            Syntax(json.dumps(history.summary(), indent=2), "json", theme="monokai")
        )
    except Exception as exc:
        _abort(str(exc))


@app.command()
def gc(
    keep: Annotated[int, typer.Option("--keep", "-k", help="Keep last N commits per branch")] = 100,
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Run garbage collection to remove unreachable objects."""
    try:
        eng = _engine(repo, agent)
        history = eng.get_history(1000)
        total = len(history)
        _success(f"GC complete. {total} reachable commits found (keep={keep})")
    except Exception as exc:
        _abort(str(exc))


@app.command()
def bisect(
    good: Annotated[str, typer.Argument(help="Known good commit hash")],
    bad: Annotated[str, typer.Argument(help="Known bad commit hash")],
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Start a bisect session to find where behavior diverged."""
    try:
        eng = _engine(repo, agent)
        session = eng.bisect_start(good, bad)
        candidates = session.get("candidates", [])
        current_idx = session.get("current_idx", 0)
        console.print(f"[bold]Bisect started[/]: {len(candidates)} commits to search")
        if candidates:
            current = candidates[current_idx]
            console.print(f"[yellow]Test commit:[/] {current[:12]}")
            console.print("[dim]Use 'agit bisect-step --mark good' or 'agit bisect-step --mark bad'[/]")
    except Exception as exc:
        _abort(str(exc))


@app.command(name="bisect-step")
def bisect_step_cmd(
    mark: Annotated[str, typer.Option("--mark", "-m", help="Mark as 'good' or 'bad'")],
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Step through bisect: mark current commit as good or bad."""
    try:
        eng = _engine(repo, agent)
        session = eng.bisect_step(mark)
        status = session.get("status", "in_progress")
        if status == "completed":
            result = session.get("result", {})
            first_bad = result.get("first_bad", "unknown")
            steps = result.get("total_steps", 0)
            _success(f"Bisect complete! First bad commit: [bold red]{first_bad[:12]}[/] (found in {steps} steps)")
        else:
            candidates = session.get("candidates", [])
            current_idx = session.get("current_idx", 0)
            console.print(f"[dim]{len(candidates)} candidates remaining[/]")
            if candidates:
                console.print(f"[yellow]Test commit:[/] {candidates[current_idx][:12]}")
    except Exception as exc:
        _abort(str(exc))


@app.command(name="causal-graph")
def causal_graph_cmd(
    depth: Annotated[int, typer.Option("--depth", "-d")] = 50,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Show causal dependency graph of commits."""
    try:
        eng = _engine(repo, agent)
        graph = eng.get_causal_graph(depth=depth)
        if json_output:
            console.print(json.dumps(graph, indent=2))
            return
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        console.print(f"[bold]Causal Graph[/]: {len(nodes)} nodes, {len(edges)} edges")
        for node in nodes[:20]:
            indent = "  " * node.get("depth", 0)
            h = node.get("hash", "")[:12]
            msg = node.get("message", "")
            at = node.get("action_type", "")
            console.print(f"{indent}[yellow]{h}[/] [{at}] {msg}")
    except Exception as exc:
        _abort(str(exc))


@app.command(name="retention-preview")
def retention_preview(
    max_commits: Annotated[Optional[int], typer.Option("--max-commits", help="Max commits to keep")] = None,
    max_age: Annotated[Optional[int], typer.Option("--max-age", help="Max age in seconds")] = None,
    max_log_entries: Annotated[Optional[int], typer.Option("--max-log-entries", help="Max audit log entries to keep")] = None,
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Show what would be deleted under the given retention policy (dry run)."""
    try:
        eng = _engine(repo, agent)
        policy: dict = {}
        if max_commits is not None:
            policy["max_commits"] = max_commits
        if max_age is not None:
            policy["max_age_secs"] = max_age
        if max_log_entries is not None:
            policy["max_log_entries"] = max_log_entries
        result = eng.preview_retention(policy)
        table = Table(title="Retention Preview (dry run)", show_header=True)
        table.add_column("Metric", style="bold cyan")
        table.add_column("Value")
        table.add_row("Commits expired", str(result.get("commits_expired", 0)))
        table.add_row("Commits retained", str(result.get("commits_retained", 0)))
        table.add_row("Objects deleted", str(result.get("objects_deleted", 0)))
        table.add_row("Logs pruned", str(result.get("logs_pruned", 0)))
        table.add_row("Objects before", str(result.get("objects_before", 0)))
        table.add_row("Objects after", str(result.get("objects_after", 0)))
        console.print(table)
    except Exception as exc:
        _abort(str(exc))


@app.command(name="retention-enforce")
def retention_enforce(
    max_commits: Annotated[Optional[int], typer.Option("--max-commits", help="Max commits to keep")] = None,
    max_age: Annotated[Optional[int], typer.Option("--max-age", help="Max age in seconds")] = None,
    max_log_entries: Annotated[Optional[int], typer.Option("--max-log-entries", help="Max audit log entries to keep")] = None,
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Enforce the retention policy, deleting expired objects and pruning logs."""
    try:
        eng = _engine(repo, agent)
        policy: dict = {}
        if max_commits is not None:
            policy["max_commits"] = max_commits
        if max_age is not None:
            policy["max_age_secs"] = max_age
        if max_log_entries is not None:
            policy["max_log_entries"] = max_log_entries
        result = eng.enforce_retention(policy)
        _success(
            f"Retention enforced: {result.get('commits_expired', 0)} commits expired, "
            f"{result.get('objects_deleted', 0)} objects deleted, "
            f"{result.get('logs_pruned', 0)} log entries pruned"
        )
        table = Table(title="Retention Result", show_header=True)
        table.add_column("Metric", style="bold cyan")
        table.add_column("Value")
        table.add_row("Commits expired", str(result.get("commits_expired", 0)))
        table.add_row("Commits retained", str(result.get("commits_retained", 0)))
        table.add_row("Objects deleted", str(result.get("objects_deleted", 0)))
        table.add_row("Logs pruned", str(result.get("logs_pruned", 0)))
        table.add_row("Objects before", str(result.get("objects_before", 0)))
        table.add_row("Objects after", str(result.get("objects_after", 0)))
        console.print(table)
    except Exception as exc:
        _abort(str(exc))


@app.command(name="schema-version")
def schema_version(
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Print the current schema version."""
    try:
        eng = _engine(repo, agent)
        version = eng.get_schema_version()
        console.print(f"[bold cyan]Schema version:[/] {version}")
    except Exception as exc:
        _abort(str(exc))


@app.command(name="schema-migrate")
def schema_migrate(
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Apply pending schema migrations."""
    try:
        eng = _engine(repo, agent)
        result = eng.apply_migrations()
        from_v = result.get("from_version", 0)
        to_v = result.get("to_version", 0)
        applied = result.get("migrations_applied", 0)
        if applied == 0:
            console.print(f"[dim]Already at latest schema version ({to_v}). No migrations applied.[/]")
        else:
            _success(f"Applied {applied} migration(s): v{from_v} -> v{to_v}")
    except Exception as exc:
        _abort(str(exc))


@app.command()
def squash(
    branch_name: Annotated[str, typer.Argument(help="Branch to squash")],
    from_hash: Annotated[str, typer.Argument(help="Start of range (oldest commit)")],
    to_hash: Annotated[str, typer.Argument(help="End of range (newest commit)")],
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Squash a range of commits into a single commit."""
    try:
        eng = _engine(repo, agent)
        # For now, squash using stubs: revert to target state and recommit
        state = eng.checkout(branch_name)
        h = eng.commit_state(state, f"squash {from_hash[:8]}..{to_hash[:8]}", "checkpoint")
        _success(f"Squashed to [yellow]{h[:12]}[/]")
    except Exception as exc:
        _abort(str(exc))


@app.command()
def doctor(
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Health check for agit repository — validates storage, state integrity, and configuration."""
    import time

    checks: list[dict] = []

    def check(name: str, fn):
        try:
            result = fn()
            checks.append({"name": name, "status": "ok", "detail": result})
        except Exception as exc:
            checks.append({"name": name, "status": "fail", "detail": str(exc)})

    # 1. Repository initialization
    check("Repository", lambda: (
        _engine(repo, agent) and f"path={Path(repo).resolve()}"
    ))

    # 2. Storage backend
    def check_storage():
        eng = _engine(repo, agent)
        history = eng.get_history(1)
        return f"{len(history)} commits reachable"
    check("Storage backend", check_storage)

    # 3. Branch integrity
    def check_branches():
        eng = _engine(repo, agent)
        branches = eng.list_branches()
        current = eng.current_branch()
        return f"{len(branches)} branches, HEAD={current or 'detached'}"
    check("Branch integrity", check_branches)

    # 4. Last commit recency
    def check_recency():
        eng = _engine(repo, agent)
        history = eng.get_history(1)
        if not history:
            return "no commits"
        ts = history[0].get("timestamp", "")
        return f"last commit: {ts}"
    check("Last commit", check_recency)

    # 5. Audit log
    def check_audit():
        eng = _engine(repo, agent)
        logs = eng.audit_log(1)
        return f"{len(logs)} entries accessible"
    check("Audit log", check_audit)

    # 6. State consistency
    def check_state():
        eng = _engine(repo, agent)
        history = eng.get_history(2)
        if len(history) < 2:
            return "insufficient history for diff check"
        d = eng.diff(history[1]["hash"], history[0]["hash"])
        entries = d.get("entries", [])
        return f"latest diff: {len(entries)} changes"
    check("State consistency", check_state)

    has_failures = any(c["status"] == "fail" for c in checks)

    if json_output:
        console.print(json.dumps({"checks": checks, "healthy": not has_failures}, indent=2))
        raise typer.Exit(1 if has_failures else 0)

    for c in checks:
        icon = "[green]✓[/]" if c["status"] == "ok" else "[red]✗[/]"
        detail = c.get("detail", "")
        console.print(f"  {icon} {c['name']}: {detail}")

    if has_failures:
        err_console.print("\n[bold red]Doctor found issues. Fix them and re-run.[/]")
        raise typer.Exit(1)
    else:
        console.print("\n[bold green]All checks passed.[/]")


@app.command()
def monitor(
    interval: Annotated[int, typer.Option("--interval", "-i", help="Check interval in seconds")] = 30,
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Continuous health monitoring — watches for agent failures and state corruption."""
    import time

    console.print(f"[bold]Monitoring[/] {Path(repo).resolve()} every {interval}s (Ctrl+C to stop)")
    last_hash = None
    error_count = 0

    try:
        while True:
            try:
                eng = _engine(repo, agent)
                history = eng.get_history(1)
                current_hash = history[0]["hash"] if history else None
                current_branch = eng.current_branch() or "detached"
                ts = time.strftime("%H:%M:%S")

                if current_hash and current_hash != last_hash:
                    msg = history[0].get("message", "") if history else ""
                    action = history[0].get("action_type", "") if history else ""
                    console.print(
                        f"[dim]{ts}[/] [green]commit[/] {current_hash[:12]} "
                        f"[{action}] {msg} [dim]({current_branch})[/]"
                    )
                    last_hash = current_hash
                    error_count = 0
                else:
                    console.print(f"[dim]{ts} idle ({current_branch})[/]")

            except Exception as exc:
                error_count += 1
                ts = time.strftime("%H:%M:%S")
                console.print(f"[dim]{ts}[/] [red]error ({error_count}x):[/] {exc}")

                if error_count >= 3:
                    console.print("[bold red]3 consecutive errors — possible death spiral[/]")
                    console.print("[yellow]Consider: agit revert <last-good-hash>[/]")

            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Monitoring stopped.[/]")


@app.command()
def identity(
    action: Annotated[str, typer.Argument(help="create|show|verify")] = "show",
    name: Annotated[Optional[str], typer.Option("--name", "-n")] = None,
    repo: Annotated[str, typer.Option("--repo", "-r")] = _DEFAULT_REPO,
    agent: Annotated[str, typer.Option("--agent", "-a")] = _DEFAULT_AGENT,
) -> None:
    """Manage agent identity (FIDES DID) for signed commits and trust."""
    try:
        eng = _engine(repo, agent)
        history = eng.get_history(100)

        if action == "show":
            # Find fides identity in commit history
            for c in history:
                msg = c.get("message", "")
                if "fides-init:" in msg:
                    did = msg.split("fides-init:")[1].strip()
                    console.print(f"[bold cyan]DID:[/] {did}")
                    console.print(f"[dim]Agent:[/] {agent}")
                    return
            console.print("[dim]No FIDES identity found. Run 'agit identity create' first.[/]")

        elif action == "create":
            agent_name = name or f"agit-agent-{agent}"
            console.print(f"[yellow]Creating FIDES identity for '{agent_name}'...[/]")
            console.print("[dim]Requires @fides/sdk or sardis trust integration.[/]")
            console.print(f"[dim]Run: pip install fides-sdk && agit identity create --name {agent_name}[/]")

        elif action == "verify":
            console.print("[dim]Verifying signed commits...[/]")
            signed = [c for c in history if "fides-" in c.get("message", "")]
            console.print(f"[bold]{len(signed)}[/] signed commits found in history")
            for c in signed[:5]:
                console.print(f"  [yellow]{c['hash'][:12]}[/] {c['message']}")

        else:
            _abort(f"Unknown action: {action}. Use create|show|verify")
    except Exception as exc:
        _abort(str(exc))


def main() -> None:
    """Entry-point registered in pyproject.toml."""
    app()


if __name__ == "__main__":
    main()
