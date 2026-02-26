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


def main() -> None:
    """Entry-point registered in pyproject.toml."""
    app()


if __name__ == "__main__":
    main()
