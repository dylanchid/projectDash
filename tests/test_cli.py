from __future__ import annotations

import pytest

from projectdash import cli
from projectdash.errors import AuthenticationError, PersistenceError


def test_pd_dev_dispatches_to_dev_runner(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["pd", "dev"])
    monkeypatch.setattr(cli, "load_project_env", lambda: None)
    monkeypatch.setattr(cli, "run_dev", lambda: 0)

    with pytest.raises(SystemExit) as raised:
        cli.main()

    assert raised.value.code == 0


@pytest.mark.asyncio
async def test_sync_prints_success_summary_and_diagnostics(monkeypatch, capsys) -> None:
    class FakeDataManager:
        def __init__(self):
            self.last_sync_result = "idle"

        async def initialize(self):
            return None

        async def sync_with_linear(self):
            self.last_sync_result = "success"

        def sync_status_summary(self) -> str:
            return "success u:1 p:1 i:2 t:1"

        def sync_diagnostic_lines(self) -> list[str]:
            return ["auth: ok: Tester", "issues: ok: 2"]

    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    monkeypatch.setattr(cli, "DataManager", FakeDataManager)

    rc = await cli.sync()
    out = capsys.readouterr().out

    assert rc == 0
    assert "✅ Sync complete. success u:1 p:1 i:2 t:1" in out
    assert "connector scope: linear" in out
    assert "failure category: none" in out
    assert "   - auth: ok: Tester" in out
    assert "   - issues: ok: 2" in out


@pytest.mark.asyncio
async def test_sync_prints_failure_summary_and_diagnostics(monkeypatch, capsys) -> None:
    class FakeDataManager:
        def __init__(self):
            self.last_sync_result = "idle"

        async def initialize(self):
            return None

        async def sync_with_linear(self):
            self.last_sync_result = "failed"

        def sync_status_summary(self) -> str:
            return "failed: issues fetch failed: rate limit"

        def sync_diagnostic_lines(self) -> list[str]:
            return ["auth: ok: Tester", "issues: failed: rate limit"]

    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    monkeypatch.setattr(cli, "DataManager", FakeDataManager)

    rc = await cli.sync()
    out = capsys.readouterr().out

    assert rc == 1
    assert "❌ Sync failed. failed: issues fetch failed: rate limit" in out
    assert "connector scope: linear" in out
    assert "failure category: rate_limit" in out
    assert "retry hint:" in out
    assert "   - issues: failed: rate limit" in out


@pytest.mark.asyncio
async def test_sync_handles_connector_exception_and_returns_nonzero(monkeypatch, capsys) -> None:
    class FakeDataManager:
        def __init__(self):
            self.last_sync_result = "idle"
            self.last_sync_error = ""
            self.sync_diagnostics = {"linear_fetch": "failed: timeout"}

        async def initialize(self):
            return None

        async def sync_with_linear(self):
            raise RuntimeError("timeout while fetching issues")

        def sync_status_summary(self) -> str:
            return "failed: timeout while fetching issues"

        def sync_diagnostic_lines(self) -> list[str]:
            return ["linear_fetch: failed: timeout"]

    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    monkeypatch.setattr(cli, "DataManager", FakeDataManager)

    rc = await cli.sync()
    out = capsys.readouterr().out

    assert rc == 1
    assert "❌ Sync failed." in out
    assert "connector scope: linear" in out
    assert "failure category: network" in out
    assert "linear_fetch: failed: timeout" in out


@pytest.mark.asyncio
async def test_sync_github_prints_success_summary_and_diagnostics(monkeypatch, capsys) -> None:
    class FakeDataManager:
        def __init__(self):
            self.last_sync_result = "idle"

        async def initialize(self):
            return None

        async def sync_with_github(self):
            self.last_sync_result = "success"

        def sync_status_summary(self) -> str:
            return "success r:1 pr:2 c:4"

        def sync_diagnostic_lines(self) -> list[str]:
            return ["github_auth: ok: octocat", "github_repo:acme/platform: ok: prs=2 checks=4"]

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(cli, "DataManager", FakeDataManager)

    rc = await cli.sync_github()
    out = capsys.readouterr().out

    assert rc == 0
    assert "✅ Sync complete. success r:1 pr:2 c:4" in out
    assert "connector scope: github" in out
    assert "failure category: none" in out
    assert "github_auth: ok: octocat" in out


@pytest.mark.asyncio
async def test_sync_github_requires_token(monkeypatch, capsys) -> None:
    class FakeDataManager:
        async def initialize(self):
            return None

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli, "DataManager", FakeDataManager)

    rc = await cli.sync_github()
    out = capsys.readouterr().out

    assert rc == 1
    assert "❌ Error: GITHUB_TOKEN not found in environment." in out
    assert "failure category: auth" in out


@pytest.mark.asyncio
async def test_sync_github_handles_connector_exception_and_returns_nonzero(monkeypatch, capsys) -> None:
    class FakeDataManager:
        def __init__(self):
            self.last_sync_result = "idle"
            self.last_sync_error = ""
            self.sync_diagnostics = {"github_repo:acme/platform": "failed: unknown host"}

        async def initialize(self):
            return None

        async def sync_with_github(self):
            raise RuntimeError("unknown host api.github.com")

        def sync_status_summary(self) -> str:
            return "failed: unknown host"

        def sync_diagnostic_lines(self) -> list[str]:
            return ["github_repo:acme/platform: failed: unknown host"]

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(cli, "DataManager", FakeDataManager)

    rc = await cli.sync_github()
    out = capsys.readouterr().out

    assert rc == 1
    assert "❌ Sync failed." in out
    assert "connector scope: github" in out
    assert "failure category: network" in out
    assert "github_repo:acme/platform: failed: unknown host" in out


@pytest.mark.asyncio
async def test_sync_uses_typed_auth_error_category(monkeypatch, capsys) -> None:
    class FakeDataManager:
        def __init__(self):
            self.last_sync_result = "idle"
            self.last_sync_error = ""
            self.sync_diagnostics = {}

        async def initialize(self):
            return None

        async def sync_with_linear(self):
            raise AuthenticationError("invalid token", "linear", "auth")

        def sync_status_summary(self) -> str:
            return "failed: invalid token"

        def sync_diagnostic_lines(self) -> list[str]:
            return []

    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    monkeypatch.setattr(cli, "DataManager", FakeDataManager)

    rc = await cli.sync()
    out = capsys.readouterr().out

    assert rc == 1
    assert "failure category: auth" in out


@pytest.mark.asyncio
async def test_sync_github_uses_typed_persistence_error_category(monkeypatch, capsys) -> None:
    class FakeDataManager:
        def __init__(self):
            self.last_sync_result = "idle"
            self.last_sync_error = ""
            self.sync_diagnostics = {}

        async def initialize(self):
            return None

        async def sync_with_github(self):
            raise PersistenceError("database is locked", "github.persist")

        def sync_status_summary(self) -> str:
            return "failed: database is locked"

        def sync_diagnostic_lines(self) -> list[str]:
            return []

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(cli, "DataManager", FakeDataManager)

    rc = await cli.sync_github()
    out = capsys.readouterr().out

    assert rc == 1
    assert "failure category: storage" in out


@pytest.mark.asyncio
async def test_sync_history_prints_entries(monkeypatch, capsys) -> None:
    class FakeDataManager:
        async def initialize(self):
            return None

        def get_sync_history(self, limit: int = 20) -> list[dict]:
            assert limit == 20
            return [
                {
                    "created_at": "2026-02-23 01:00:00",
                    "result": "failed",
                    "summary": "failed: issues fetch failed: rate limit",
                    "diagnostics": {"issues": "failed: rate limit"},
                }
            ]

    monkeypatch.setattr(cli, "DataManager", FakeDataManager)
    rc = await cli.sync_history()
    out = capsys.readouterr().out

    assert rc == 1
    assert "🕘 Recent Sync History" in out
    assert "2026-02-23 01:00:00 | failed | failed: issues fetch failed: rate limit" in out
    assert "connector scope: linear" in out
    assert "failure category: rate_limit" in out
    assert "   - issues: failed: rate limit" in out


@pytest.mark.asyncio
async def test_sync_history_detects_github_scope_from_diagnostics(monkeypatch, capsys) -> None:
    class FakeDataManager:
        async def initialize(self):
            return None

        def get_sync_history(self, limit: int = 20) -> list[dict]:
            assert limit == 20
            return [
                {
                    "created_at": "2026-02-23 01:00:00",
                    "result": "failed",
                    "summary": "failed: github repo fetch failed",
                    "diagnostics": {"github_repo:acme/platform": "failed: rate limit"},
                }
            ]

    monkeypatch.setattr(cli, "DataManager", FakeDataManager)
    rc = await cli.sync_history()
    out = capsys.readouterr().out

    assert rc == 1
    assert "connector scope: github" in out
    assert "failure category: rate_limit" in out


@pytest.mark.asyncio
async def test_sync_requires_linear_api_key_returns_nonzero(monkeypatch, capsys) -> None:
    class FakeDataManager:
        async def initialize(self):
            return None

    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.setattr(cli, "DataManager", FakeDataManager)

    rc = await cli.sync()
    out = capsys.readouterr().out

    assert rc == 1
    assert "LINEAR_API_KEY not found" in out
    assert "failure category: auth" in out


@pytest.mark.asyncio
async def test_sync_history_returns_zero_when_only_success(monkeypatch, capsys) -> None:
    class FakeDataManager:
        async def initialize(self):
            return None

        def get_sync_history(self, limit: int = 20) -> list[dict]:
            assert limit == 20
            return [
                {
                    "created_at": "2026-02-23 01:00:00",
                    "result": "success",
                    "summary": "success u:1 p:1 i:2 t:1",
                    "diagnostics": {"auth": "ok: Tester"},
                }
            ]

    monkeypatch.setattr(cli, "DataManager", FakeDataManager)

    rc = await cli.sync_history()
    out = capsys.readouterr().out

    assert rc == 0
    assert "Recent Sync History" in out
    assert "failure category" not in out


@pytest.mark.asyncio
async def test_connectors_prints_available_connectors(monkeypatch, capsys) -> None:
    class FakeDataManager:
        async def initialize(self):
            return None

        def available_connectors(self) -> list[str]:
            return ["github", "linear"]

    monkeypatch.setattr(cli, "DataManager", FakeDataManager)
    await cli.connectors()
    out = capsys.readouterr().out

    assert "🔌 Connectors" in out
    assert "- github" in out
    assert "- linear" in out


@pytest.mark.asyncio
async def test_agent_runs_prints_entries(monkeypatch, capsys) -> None:
    class FakeRun:
        def __init__(self) -> None:
            self.id = "run-1"
            self.status = "running"
            self.runtime = "tmux"
            self.issue_id = "PD-1"
            self.project_id = "p1"
            self.started_at = "2026-02-25 12:00:00"

    class FakeDataManager:
        async def initialize(self):
            return None

        async def get_agent_runs(self, limit: int = 20):
            assert limit == 20
            return [FakeRun()]

    monkeypatch.setattr(cli, "DataManager", FakeDataManager)
    await cli.agent_runs()
    out = capsys.readouterr().out

    assert "🤖 Recent Agent Runs" in out
    assert "run-1 | running | runtime=tmux | issue=PD-1 | project=p1" in out


@pytest.mark.asyncio
async def test_agent_run_finish_returns_nonzero_on_missing_run(monkeypatch, capsys) -> None:
    class FakeDataManager:
        async def initialize(self):
            return None

        async def complete_agent_run(self, run_id, exit_code, *, session_ref=None, log_path=None):
            assert run_id == "missing-run"
            assert exit_code == 2
            assert session_ref == "session-1"
            assert log_path == "/tmp/missing.log"
            return False, "Agent run not found: missing-run"

    monkeypatch.setattr(cli, "DataManager", FakeDataManager)
    rc = await cli.agent_run_finish(
        run_id="missing-run",
        exit_code=2,
        session_ref="session-1",
        log_path="/tmp/missing.log",
    )
    out = capsys.readouterr().out

    assert rc == 1
    assert "Agent run not found: missing-run" in out
