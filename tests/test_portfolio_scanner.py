from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from projectdash.models import LocalProject
from projectdash.services.portfolio_scanner import PortfolioScanner, compute_activity_score


def _make_project(**overrides) -> LocalProject:
    defaults = dict(
        id="local:test",
        name="test",
        path="/tmp/test",
        status="active",
        tier="C",
        type="unknown",
    )
    defaults.update(overrides)
    return LocalProject(**defaults)


def test_compute_activity_score_full():
    now = datetime.now(timezone.utc).isoformat()
    p = _make_project(has_readme=True, has_tests=True, has_ci=True, last_commit_at=now)
    assert compute_activity_score(p) == 100


def test_compute_activity_score_empty():
    p = _make_project()
    assert compute_activity_score(p) == 0


def test_compute_activity_score_readme_only():
    p = _make_project(has_readme=True)
    assert compute_activity_score(p) == 20


def test_compute_activity_score_old_commit():
    old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    p = _make_project(has_readme=True, last_commit_at=old)
    assert compute_activity_score(p) == 20


def test_compute_activity_score_recent_commit():
    recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    p = _make_project(last_commit_at=recent)
    assert compute_activity_score(p) == 30


def test_compute_activity_score_month_old_commit():
    month_old = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
    p = _make_project(last_commit_at=month_old)
    assert compute_activity_score(p) == 20


def test_compute_activity_score_quarter_old_commit():
    quarter = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    p = _make_project(last_commit_at=quarter)
    assert compute_activity_score(p) == 10


def test_scan_root_empty_dir(tmp_path):
    scanner = PortfolioScanner()
    result = scanner.scan_root(tmp_path)
    assert result == []


def test_scan_root_nonexistent_dir():
    scanner = PortfolioScanner()
    result = scanner.scan_root(Path("/nonexistent/path/abcxyz"))
    assert result == []


def test_scan_root_skips_non_git(tmp_path):
    (tmp_path / "not-a-repo").mkdir()
    scanner = PortfolioScanner()
    result = scanner.scan_root(tmp_path)
    assert result == []


def test_scan_root_skips_hidden_dirs(tmp_path):
    hidden = tmp_path / ".hidden-repo"
    hidden.mkdir()
    subprocess.run(["git", "init", str(hidden)], capture_output=True)
    scanner = PortfolioScanner()
    result = scanner.scan_root(tmp_path)
    assert result == []


def test_scan_root_detects_git_repo(tmp_path):
    repo = tmp_path / "myproject"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], capture_output=True)
    scanner = PortfolioScanner()
    result = scanner.scan_root(tmp_path)
    assert len(result) == 1
    assert result[0].id == "local:myproject"
    assert result[0].name == "myproject"
    assert result[0].path == str(repo)


def test_scan_root_detects_readme(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], capture_output=True)
    (repo / "README.md").write_text("# Hello")
    scanner = PortfolioScanner()
    result = scanner.scan_root(tmp_path)
    assert result[0].has_readme is True


def test_scan_root_detects_tests(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], capture_output=True)
    (repo / "tests").mkdir()
    scanner = PortfolioScanner()
    result = scanner.scan_root(tmp_path)
    assert result[0].has_tests is True


def test_scan_root_detects_ci(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], capture_output=True)
    (repo / ".github" / "workflows").mkdir(parents=True)
    scanner = PortfolioScanner()
    result = scanner.scan_root(tmp_path)
    assert result[0].has_ci is True


def test_manifest_round_trip_json(tmp_path):
    scanner = PortfolioScanner()
    manifest_path = tmp_path / "portfolio.json"
    data = {
        "local:proj1": {"tier": "S", "status": "active"},
        "local:proj2": {"tier": "B", "status": "paused"},
    }
    scanner.save_manifest(manifest_path, data)
    loaded = scanner.load_manifest(manifest_path)
    assert loaded == data


def test_load_manifest_missing_file(tmp_path):
    scanner = PortfolioScanner()
    result = scanner.load_manifest(tmp_path / "nonexistent.json")
    assert result == {}


def test_apply_manifest_merges_fields():
    scanner = PortfolioScanner()
    projects = [
        _make_project(id="local:foo", name="foo", tier="C", status="active"),
    ]
    manifest = {
        "local:foo": {"tier": "S", "status": "shipped", "type": "tui"},
    }
    result = scanner.apply_manifest(projects, manifest)
    assert len(result) == 1
    assert result[0].tier == "S"
    assert result[0].status == "shipped"
    assert result[0].type == "tui"


def test_apply_manifest_preserves_scanned_fields():
    scanner = PortfolioScanner()
    projects = [
        _make_project(
            id="local:bar",
            name="bar",
            has_readme=True,
            has_tests=True,
            last_commit_at="2026-01-01T00:00:00+00:00",
        ),
    ]
    manifest = {"local:bar": {"tier": "A"}}
    result = scanner.apply_manifest(projects, manifest)
    assert result[0].has_readme is True
    assert result[0].has_tests is True
    assert result[0].last_commit_at == "2026-01-01T00:00:00+00:00"
    assert result[0].tier == "A"


def test_apply_manifest_no_match():
    scanner = PortfolioScanner()
    projects = [_make_project(id="local:x")]
    manifest = {"local:other": {"tier": "S"}}
    result = scanner.apply_manifest(projects, manifest)
    assert result[0].tier == "C"
