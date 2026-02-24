from __future__ import annotations

import pytest

from projectdash import cli


def test_pd_dev_dispatches_to_dev_runner(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["pd", "dev"])
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
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

    await cli.sync()
    out = capsys.readouterr().out

    assert "✅ Sync complete. success u:1 p:1 i:2 t:1" in out
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

    await cli.sync()
    out = capsys.readouterr().out

    assert "❌ Sync failed. failed: issues fetch failed: rate limit" in out
    assert "   - issues: failed: rate limit" in out


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
    await cli.sync_history()
    out = capsys.readouterr().out

    assert "🕘 Recent Sync History" in out
    assert "2026-02-23 01:00:00 | failed | failed: issues fetch failed: rate limit" in out
    assert "   - issues: failed: rate limit" in out
