from projectdash.views.sync_history import SyncHistoryScreen


def test_entry_recovery_hints_include_token_setup_steps() -> None:
    entry = {
        "summary": "failed: GITHUB_TOKEN not set",
        "diagnostics": {"github_auth": "failed: GITHUB_TOKEN not set"},
    }

    hints = SyncHistoryScreen._entry_recovery_hints(entry)

    assert any("GITHUB_TOKEN" in hint for hint in hints)


def test_entry_recovery_hints_fallback_for_generic_failures() -> None:
    entry = {
        "summary": "failed: unknown transport error",
        "diagnostics": {"github_repo:acme/api": "failed: timeout"},
    }

    hints = SyncHistoryScreen._entry_recovery_hints(entry)

    assert hints
    assert "retry" in hints[-1].casefold() or "fix connector config" in hints[-1].casefold()
