import argparse
import asyncio
import os
import sys
import subprocess
from pathlib import Path
from projectdash.data import DataManager
from projectdash.database import DB_PATH
from projectdash.env import load_project_env
from projectdash.config import AppConfig
from projectdash.enums import SyncResult
from projectdash.errors import AuthenticationError, PersistenceError, ProjectDashError

def main():
    load_project_env()
    parser = argparse.ArgumentParser(description="ProjectDash CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    # Subcommands
    subparsers.add_parser("sync", help="Sync with Linear")
    subparsers.add_parser("sync-github", help="Sync with GitHub")
    subparsers.add_parser("sync-history", help="Show recent sync history")
    subparsers.add_parser("connectors", help="List configured data connectors")
    subparsers.add_parser("agent-runs", help="Show recent persisted agent runs")
    agent_run_finish_parser = subparsers.add_parser("agent-run-finish", help=argparse.SUPPRESS)
    agent_run_finish_parser.add_argument("--run-id", required=True)
    agent_run_finish_parser.add_argument("--exit-code", required=True, type=int)
    agent_run_finish_parser.add_argument("--session-ref", default=None)
    agent_run_finish_parser.add_argument("--log-path", default=None)
    subparsers.add_parser("doctor", help="Check setup and environment")
    subparsers.add_parser("stats", help="Show project statistics")
    subparsers.add_parser("test", help="Run project tests")
    subparsers.add_parser("build", help="Build the project")
    subparsers.add_parser("dev", help="Run TUI dev mode with auto-restart")
    
    args = parser.parse_args()
    
    if args.command == "sync":
        sys.exit(asyncio.run(sync()))
    elif args.command == "sync-github":
        sys.exit(asyncio.run(sync_github()))
    elif args.command == "sync-history":
        sys.exit(asyncio.run(sync_history()))
    elif args.command == "connectors":
        asyncio.run(connectors())
    elif args.command == "agent-runs":
        asyncio.run(agent_runs())
    elif args.command == "agent-run-finish":
        sys.exit(
            asyncio.run(
                agent_run_finish(
                    run_id=args.run_id,
                    exit_code=args.exit_code,
                    session_ref=args.session_ref,
                    log_path=args.log_path,
                )
            )
        )
    elif args.command == "doctor":
        doctor()
    elif args.command == "stats":
        asyncio.run(stats())
    elif args.command == "test":
        run_tests()
    elif args.command == "build":
        build_project()
    elif args.command == "dev":
        sys.exit(run_dev())
    else:
        # Default: run the TUI
        from projectdash.app import run
        run()

async def sync() -> int:
    """Manually trigger a Linear sync."""
    connector = "linear"
    print("🔄 Syncing with Linear...")
    dm = DataManager()
    await dm.initialize()
    if not os.getenv("LINEAR_API_KEY"):
        print("❌ Error: LINEAR_API_KEY not found in environment.")
        print("   - connector scope: linear")
        print("   - failure category: auth")
        print("   - retry hint: set LINEAR_API_KEY and run pd sync")
        return 1
    
    sync_error: Exception | None = None
    try:
        await dm.sync_with_linear()
    except ProjectDashError as error:
        sync_error = error
    except Exception as error:
        sync_error = error
    if dm.last_sync_result == SyncResult.SUCCESS:
        print(f"✅ Sync complete. {dm.sync_status_summary()}")
        print("   - connector scope: linear")
        print("   - failure category: none")
        print("   - retry hint: n/a")
        rc = 0
    else:
        summary = dm.sync_status_summary()
        if sync_error is not None:
            summary = f"{summary}: {sync_error}" if summary else str(sync_error)
        print(f"❌ Sync failed. {summary}")
        diagnostics = getattr(dm, "sync_diagnostics", {}) or {}
        error_text = getattr(dm, "last_sync_error", "") or (str(sync_error) if sync_error is not None else summary)
        category = _failure_category(error_text, diagnostics, sync_error)
        print(f"   - connector scope: {connector}")
        print(f"   - failure category: {category}")
        print(f"   - retry hint: {_retry_hint(connector, category)}")
        rc = 1
    for line in dm.sync_diagnostic_lines():
        print(f"   - {line}")
    return rc


async def sync_github() -> int:
    """Manually trigger a GitHub sync."""
    connector = "github"
    print("🔄 Syncing with GitHub...")
    dm = DataManager()
    await dm.initialize()
    if not os.getenv("GITHUB_TOKEN"):
        print("❌ Error: GITHUB_TOKEN not found in environment.")
        print("   - connector scope: github")
        print("   - failure category: auth")
        print("   - retry hint: set GITHUB_TOKEN and run pd sync-github")
        return 1
    sync_error: Exception | None = None
    try:
        await dm.sync_with_github()
    except ProjectDashError as error:
        sync_error = error
    except Exception as error:
        sync_error = error
    if dm.last_sync_result == SyncResult.SUCCESS:
        print(f"✅ Sync complete. {dm.sync_status_summary()}")
        print("   - connector scope: github")
        print("   - failure category: none")
        print("   - retry hint: n/a")
        rc = 0
    else:
        summary = dm.sync_status_summary()
        if sync_error is not None:
            summary = f"{summary}: {sync_error}" if summary else str(sync_error)
        print(f"❌ Sync failed. {summary}")
        diagnostics = getattr(dm, "sync_diagnostics", {}) or {}
        error_text = getattr(dm, "last_sync_error", "") or (str(sync_error) if sync_error is not None else summary)
        category = _failure_category(error_text, diagnostics, sync_error)
        print(f"   - connector scope: {connector}")
        print(f"   - failure category: {category}")
        print(f"   - retry hint: {_retry_hint(connector, category)}")
        rc = 1
    for line in dm.sync_diagnostic_lines():
        print(f"   - {line}")
    return rc


async def sync_history() -> int:
    """Show recent persisted sync history."""
    dm = DataManager()
    await dm.initialize()
    history = dm.get_sync_history(limit=20)
    if not history:
        print("No sync history found.")
        return 0
    print("🕘 Recent Sync History")
    has_failures = False
    for entry in history:
        print(f"- {entry['created_at']} | {entry['result']} | {entry['summary']}")
        diagnostics = entry.get("diagnostics") or {}
        scope = _history_connector_scope(diagnostics)
        category = _failure_category(entry.get("summary", ""), diagnostics)
        if str(entry.get("result", "")).casefold() == SyncResult.FAILED:
            has_failures = True
            print(f"   - connector scope: {scope}")
            print(f"   - failure category: {category}")
            print(f"   - retry hint: {_retry_hint(scope, category)}")
        for step, status in diagnostics.items():
            print(f"   - {step}: {status}")
    return 1 if has_failures else 0


async def connectors():
    """List configured connectors."""
    dm = DataManager()
    await dm.initialize()
    names = dm.available_connectors()
    if not names:
        print("No connectors configured.")
        return
    print("🔌 Connectors")
    for name in names:
        print(f"- {name}")


async def agent_runs():
    """Show persisted agent runs."""
    dm = DataManager()
    await dm.initialize()
    runs = await dm.get_agent_runs(limit=20)
    if not runs:
        print("No agent runs found.")
        return
    print("🤖 Recent Agent Runs")
    for run in runs:
        issue = run.issue_id or "-"
        project = run.project_id or "-"
        print(
            f"- {run.id} | {run.status} | runtime={run.runtime} | issue={issue} | project={project} | started={run.started_at}"
        )


async def agent_run_finish(
    *,
    run_id: str,
    exit_code: int,
    session_ref: str | None = None,
    log_path: str | None = None,
) -> int:
    dm = DataManager()
    await dm.initialize()
    ok, message = await dm.complete_agent_run(
        run_id,
        exit_code,
        session_ref=session_ref,
        log_path=log_path,
    )
    print(message)
    return 0 if ok else 1

def doctor():
    """Check for necessary environment variables and files."""
    print("🩺 Running ProjectDash Doctor...")
    config = AppConfig.from_env()
    
    # 1. Check .env
    env_exists = Path(".env").exists()
    print(f"[{'✓' if env_exists else '✕'}] .env file")
    
    # 2. Check API Key
    api_key = os.getenv("LINEAR_API_KEY")
    print(f"[{'✓' if api_key else '✕'}] LINEAR_API_KEY")
    github_token = os.getenv("GITHUB_TOKEN")
    print(f"[{'✓' if github_token else '✕'}] GITHUB_TOKEN")
    github_repos = os.getenv("PD_GITHUB_REPOS", "").strip()
    configured_targets = [value.strip() for value in config.github_repositories if str(value).strip()]
    if github_repos or configured_targets:
        print("[✓] GitHub repository targets configured")
    else:
        print("[✓] GitHub repository targets: auto-discovery mode")
    agent_run_cmd = os.getenv("PD_AGENT_RUN_CMD", "").strip()
    print(f"[{'✓' if agent_run_cmd else '✕'}] PD_AGENT_RUN_CMD")
    
    # 3. Check DB
    db_exists = DB_PATH.exists()
    print(f"[{'✓' if db_exists else '✕'}] projectdash.db cache")
    
    # 4. Check Connection (optional)
    if api_key:
        print("   - Testing Linear API connection...")
        # A quick ping could go here
    
    print("\nDoctor check complete.")

async def stats():
    """Quick project statistics."""
    print("📊 ProjectDash Stats")
    dm = DataManager()
    await dm.initialize()
    
    projects = dm.get_projects()
    issues = dm.get_issues()
    
    print(f"Projects: {len(projects)}")
    print(f"Issues:   {len(issues)}")
    
    # Simple breakdown by status
    statuses = {}
    for i in issues:
        statuses[i.status] = statuses.get(i.status, 0) + 1
    
    print("\nIssue Status:")
    for status, count in statuses.items():
        print(f"  {status:12}: {count}")

def run_tests():
    """Run pytest suite."""
    print("🧪 Running tests...")
    try:
        subprocess.run(["pytest"], check=True)
    except subprocess.CalledProcessError:
        print("❌ Tests failed.")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ Error: pytest not found. Run 'uv sync' or 'uv add --dev pytest'.")

def build_project():
    """Build the project using uv."""
    print("🏗️ Building project...")
    try:
        subprocess.run(["uv", "build"], check=True)
    except subprocess.CalledProcessError:
        print("❌ Build failed.")
        sys.exit(1)


def run_dev() -> int:
    """Run the dev watcher (auto-restart + Textual dev mode)."""
    try:
        import watchfiles  # noqa: F401
    except ImportError:
        if os.getenv("PD_DEV_BOOTSTRAPPED") == "1":
            print("❌ watchfiles is not installed. Run: uv sync --group dev")
            return 1
        try:
            env = dict(os.environ)
            env["PD_DEV_BOOTSTRAPPED"] = "1"
            return subprocess.call(["uv", "run", "pd", "dev"], env=env)
        except FileNotFoundError:
            print("❌ 'uv' is required for dev bootstrap. Install uv or run from the project venv.")
            return 1

    from projectdash.dev import main as dev_main

    return dev_main()


def _failure_category(
    summary: str,
    diagnostics: dict[str, str],
    error: Exception | None = None,
) -> str:
    if isinstance(error, AuthenticationError):
        return "auth"
    if isinstance(error, PersistenceError):
        return "storage"
    if isinstance(error, ProjectDashError) and "rate limit" in str(error).casefold():
        return "rate_limit"
    haystack = " ".join(
        [summary, *(f"{step} {status}" for step, status in diagnostics.items())]
    ).casefold()
    if any(token in haystack for token in ("api_key not set", "token not set", "auth failed", "unauthorized", "forbidden")):
        return "auth"
    if "rate limit" in haystack:
        return "rate_limit"
    if any(token in haystack for token in ("timeout", "connection", "dns", "network")):
        return "network"
    if any(token in haystack for token in ("persist failed", "reload failed", "database", "sqlite")):
        return "storage"
    if "unknown host" in haystack:
        return "network"
    if "no repositories configured" in haystack:
        return "config"
    return "unknown"


def _retry_hint(connector: str, category: str) -> str:
    if category == "auth":
        if connector == "github":
            return "verify GITHUB_TOKEN scopes, then rerun pd sync-github"
        return "verify LINEAR_API_KEY, then rerun pd sync"
    if category == "rate_limit":
        return "wait for provider rate-limit reset, then retry"
    if category == "network":
        return "check network connectivity and retry"
    if category == "storage":
        return "check local DB permissions/disk, then retry"
    if category == "config":
        return "set connector configuration, then retry"
    return "inspect diagnostics output and retry"


def _history_connector_scope(diagnostics: dict[str, str]) -> str:
    if any(step.startswith("github_") or step.startswith("github:") for step in diagnostics):
        return "github"
    return "linear"

if __name__ == "__main__":
    main()
