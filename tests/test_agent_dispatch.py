from __future__ import annotations

from pathlib import Path

import pytest

from projectdash.config import AppConfig
from projectdash.data import DataManager
from projectdash.models import AgentRun


def _agent_run() -> AgentRun:
    return AgentRun(
        id="ghrun-abc123",
        runtime="github-manual",
        status="queued",
        started_at="2026-02-26 10:00:00",
        issue_id="PD-12",
        project_id="p1",
        branch_name="feature/dispatch",
        pr_id="github:acme/api:pr:12",
        prompt_text="Review PR #12",
        artifacts={
            "repository_id": "github:acme/api",
            "pull_request_number": 12,
            "pull_request_url": "https://github.com/acme/api/pull/12",
            "head_branch": "feature/dispatch",
            "base_branch": "main",
        },
    )


@pytest.mark.asyncio
async def test_dispatch_agent_run_returns_queued_when_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("PD_AGENT_RUN_CMD", raising=False)
    dm = DataManager(config=AppConfig(seed_mock_data=False))
    run = _agent_run()

    dispatched, message = await dm.dispatch_agent_run(run)

    assert dispatched is False
    assert "queued only" in message
    assert run.status == "queued"


@pytest.mark.asyncio
async def test_dispatch_agent_run_marks_running_and_records(monkeypatch) -> None:
    monkeypatch.setenv("PD_AGENT_RUN_CMD", "echo {run_id} {issue_id} {pull_request_number}")
    dm = DataManager(config=AppConfig(seed_mock_data=False))
    run = _agent_run()
    saved_statuses: list[str] = []
    command_calls: list[list[str]] = []

    async def fake_record_agent_run(saved_run: AgentRun) -> None:
        saved_statuses.append(saved_run.status)

    class _FakeProcess:
        pid = 98765

    def fake_popen(command_parts, **kwargs):
        command_calls.append(command_parts)
        return _FakeProcess()

    monkeypatch.setattr(dm, "record_agent_run", fake_record_agent_run)
    monkeypatch.setattr("projectdash.data.shutil.which", lambda name: "/bin/echo" if name == "echo" else None)
    monkeypatch.setattr("projectdash.data.subprocess.Popen", fake_popen)

    dispatched, message = await dm.dispatch_agent_run(run)

    assert dispatched is True
    assert "pid=98765" in message
    assert run.status == "running"
    assert run.session_ref == "98765"
    assert saved_statuses == ["running"]
    assert command_calls == [["echo", "ghrun-abc123", "PD-12", "12"]]


@pytest.mark.asyncio
async def test_dispatch_agent_run_tmux_profile_captures_session_and_log(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PD_AGENT_RUN_CMD", "tmux:echo run={run_id} pr={pull_request_number}")
    dm = DataManager(config=AppConfig(seed_mock_data=False))
    run = _agent_run()
    saved_runs: list[AgentRun] = []
    command_calls: list[list[str]] = []

    async def fake_record_agent_run(saved_run: AgentRun) -> None:
        saved_runs.append(saved_run)

    class _FakeProcess:
        pid = 12345

    def fake_popen(command_parts, **kwargs):
        command_calls.append(command_parts)
        return _FakeProcess()

    monkeypatch.setattr(dm, "record_agent_run", fake_record_agent_run)
    monkeypatch.setattr("projectdash.data.shutil.which", lambda name: "/usr/bin/tmux" if name == "tmux" else None)
    monkeypatch.setattr("projectdash.data.subprocess.Popen", fake_popen)

    dispatched, message = await dm.dispatch_agent_run(run)

    assert dispatched is True
    assert "tmux session=" in message
    assert run.status == "running"
    assert run.runtime == "tmux"
    assert run.session_ref is not None
    assert run.session_ref.startswith("pd-agent-")
    assert run.artifacts["launcher_profile"] == "tmux"
    assert run.artifacts["tmux_session"] == run.session_ref
    assert Path(run.artifacts["log_path"]) == tmp_path / ".projectdash" / "agent-runs" / "ghrun-abc123.log"
    launcher_script = Path(run.artifacts["launcher_script"])
    assert launcher_script.exists()
    script_body = launcher_script.read_text(encoding="utf-8")
    assert "agent-run-finish" in script_body
    assert "echo run=ghrun-abc123 pr=12" in script_body
    assert saved_runs == [run]
    assert command_calls
    assert command_calls[0][:5] == ["tmux", "new-session", "-d", "-s", run.session_ref]


@pytest.mark.asyncio
async def test_complete_agent_run_marks_failed_and_persists_artifacts(monkeypatch, tmp_path) -> None:
    dm = DataManager(config=AppConfig(seed_mock_data=False))
    run = _agent_run()
    run.status = "running"
    run.runtime = "tmux"
    run.session_ref = "pd-agent-PD-12-ghrun-abc123"
    saved_runs: list[AgentRun] = []

    async def fake_get_agent_run(run_id: str):
        if run_id == run.id:
            return run
        return None

    async def fake_record_agent_run(saved_run: AgentRun) -> None:
        saved_runs.append(saved_run)

    monkeypatch.setattr(dm.db, "get_agent_run", fake_get_agent_run)
    monkeypatch.setattr(dm, "record_agent_run", fake_record_agent_run)

    log_file = tmp_path / "agent.log"
    log_file.write_text("mock agent output", encoding="utf-8")

    ok, message = await dm.complete_agent_run(
        run.id,
        9,
        session_ref="pd-agent-PD-12-ghrun-abc123",
        log_path=str(log_file),
    )

    assert ok is True
    assert "status=failed" in message
    assert run.status == "failed"
    assert run.finished_at is not None
    assert run.error_text == "Agent run exited with code 9"
    assert run.artifacts["exit_code"] == 9
    assert run.artifacts["log_path"] == str(tmp_path / "agent.log")
    assert run.trace_logs == "mock agent output"
    assert saved_runs == [run]

@pytest.mark.asyncio
async def test_complete_agent_run_captures_trace_logs(monkeypatch, tmp_path) -> None:
    dm = DataManager(config=AppConfig(seed_mock_data=False))
    run = _agent_run()
    run.status = "running"
    
    log_file = tmp_path / "test_agent.log"
    log_file.write_text("Hello from the agent trace!", encoding="utf-8")

    async def fake_get_agent_run(run_id: str):
        if run_id == run.id:
            return run
        return None

    async def fake_record_agent_run(saved_run: AgentRun) -> None:
        pass

    monkeypatch.setattr(dm.db, "get_agent_run", fake_get_agent_run)
    monkeypatch.setattr(dm, "record_agent_run", fake_record_agent_run)

    ok, message = await dm.complete_agent_run(
        run.id,
        0,
        log_path=str(log_file),
    )

    assert ok is True
    assert run.status == "completed"
    assert run.trace_logs == "Hello from the agent trace!"

