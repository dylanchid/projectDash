from __future__ import annotations

from projectdash.views.sync_history import SyncHistoryScreen


def test_entry_search_blob_includes_diagnostics() -> None:
    entry = {
        "created_at": "2026-02-23 01:00:00",
        "result": "failed",
        "summary": "failed: issues fetch failed: rate limit",
        "diagnostics": {"issues": "failed: rate limit"},
    }

    blob = SyncHistoryScreen._entry_search_blob(entry)

    assert "2026-02-23" in blob
    assert "failed: issues fetch failed: rate limit" in blob
    assert "issues failed: rate limit" in blob


def test_filtered_entries_matches_summary_and_diagnostics() -> None:
    entries = [
        {
            "created_at": "2026-02-23 01:00:00",
            "result": "failed",
            "summary": "failed: issues fetch failed: rate limit",
            "diagnostics": {"issues": "failed: rate limit"},
        },
        {
            "created_at": "2026-02-23 00:59:00",
            "result": "success",
            "summary": "success u:1 p:1 i:2 t:1",
            "diagnostics": {"auth": "ok: tester"},
        },
    ]

    summary_match = SyncHistoryScreen._filtered_entries(entries, "u:1 p:1")
    diag_match = SyncHistoryScreen._filtered_entries(entries, "auth ok")

    assert len(summary_match) == 1
    assert summary_match[0]["result"] == "success"
    assert len(diag_match) == 1
    assert diag_match[0]["result"] == "success"
