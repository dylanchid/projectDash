from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from projectdash.config import AppConfig
from projectdash.database import Database
from projectdash.models import LocalProject
from projectdash.services.metrics import MetricsService


# --- Database round-trip tests ---


@pytest.mark.asyncio
async def test_local_projects_table_created(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.init_db()
    import aiosqlite

    async with aiosqlite.connect(tmp_path / "test.db") as conn:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cursor:
            tables = {row[0] for row in await cursor.fetchall()}
    assert "local_projects" in tables


@pytest.mark.asyncio
async def test_local_projects_round_trip(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.init_db()
    projects = [
        LocalProject(
            id="local:foo",
            name="foo",
            path="/tmp/foo",
            status="active",
            tier="S",
            type="tui",
            tags=["python", "textual"],
            description="A test project",
            last_commit_at="2026-03-01T12:00:00+00:00",
            has_readme=True,
            has_tests=True,
            has_ci=False,
            linked_linear_id="proj-123",
            linked_repo="user/foo",
            created_at="2026-01-01T00:00:00+00:00",
        ),
        LocalProject(
            id="local:bar",
            name="bar",
            path="/tmp/bar",
        ),
    ]
    await db.save_local_projects(projects)
    loaded = await db.get_local_projects()
    assert len(loaded) == 2

    foo = next(p for p in loaded if p.id == "local:foo")
    assert foo.name == "foo"
    assert foo.tier == "S"
    assert foo.type == "tui"
    assert foo.tags == ["python", "textual"]
    assert foo.has_readme is True
    assert foo.has_tests is True
    assert foo.has_ci is False
    assert foo.linked_linear_id == "proj-123"
    assert foo.linked_repo == "user/foo"

    bar = next(p for p in loaded if p.id == "local:bar")
    assert bar.tier == "C"
    assert bar.status == "active"
    assert bar.tags == []


@pytest.mark.asyncio
async def test_local_projects_upsert(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.init_db()
    p = LocalProject(id="local:x", name="x", path="/tmp/x", tier="C")
    await db.save_local_projects([p])
    p.tier = "S"
    await db.save_local_projects([p])
    loaded = await db.get_local_projects()
    assert len(loaded) == 1
    assert loaded[0].tier == "S"


@pytest.mark.asyncio
async def test_local_projects_ordered_by_tier_then_name(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.init_db()
    projects = [
        LocalProject(id="local:z", name="z", path="/z", tier="B"),
        LocalProject(id="local:a", name="a", path="/a", tier="A"),
        LocalProject(id="local:m", name="m", path="/m", tier="A"),
    ]
    await db.save_local_projects(projects)
    loaded = await db.get_local_projects()
    names = [p.name for p in loaded]
    assert names == ["a", "m", "z"]


# --- Config tests ---


def test_portfolio_root_from_env(monkeypatch):
    monkeypatch.setenv("PD_PORTFOLIO_ROOT", "/home/dev/projects")
    monkeypatch.setenv("PD_CONFIG_PATH", "/nonexistent/config.json")
    config = AppConfig.from_env()
    assert config.portfolio_root == "/home/dev/projects"


def test_portfolio_manifest_path_from_env(monkeypatch):
    monkeypatch.setenv("PD_PORTFOLIO_MANIFEST", "/custom/path.yaml")
    monkeypatch.setenv("PD_CONFIG_PATH", "/nonexistent/config.json")
    config = AppConfig.from_env()
    assert config.portfolio_manifest_path == "/custom/path.yaml"


def test_portfolio_config_defaults(monkeypatch):
    monkeypatch.setenv("PD_CONFIG_PATH", "/nonexistent/config.json")
    monkeypatch.delenv("PD_PORTFOLIO_ROOT", raising=False)
    monkeypatch.delenv("PD_PORTFOLIO_MANIFEST", raising=False)
    config = AppConfig.from_env()
    assert config.portfolio_root == ""
    assert config.portfolio_manifest_path == ""


# --- MetricsService portfolio tests ---


class DummyData:
    def __init__(self, local_projects=None):
        self._local_projects = local_projects or []

    def get_local_projects(self):
        return self._local_projects


def _make_project(**overrides):
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


def test_portfolio_empty():
    config = AppConfig()
    metrics = MetricsService(config)
    result = metrics.portfolio(DummyData())
    assert result.total == 0
    assert result.rows == []


def test_portfolio_basic_list():
    config = AppConfig()
    metrics = MetricsService(config)
    projects = [
        _make_project(id="local:a", name="a", tier="A"),
        _make_project(id="local:b", name="b", tier="B"),
    ]
    result = metrics.portfolio(DummyData(projects))
    assert result.total == 2
    assert result.rows[0].tier == "A"
    assert result.rows[1].tier == "B"


def test_portfolio_status_filter():
    config = AppConfig()
    metrics = MetricsService(config)
    projects = [
        _make_project(id="local:a", name="a", status="active"),
        _make_project(id="local:b", name="b", status="paused"),
    ]
    result = metrics.portfolio(DummyData(projects), status_filter="active")
    assert result.total == 1
    assert result.rows[0].name == "a"


def test_portfolio_ideas_filter():
    config = AppConfig()
    metrics = MetricsService(config)
    projects = [
        _make_project(id="local:a", name="a", status="idea"),
        _make_project(id="local:b", name="b", status="exploration"),
        _make_project(id="local:c", name="c", status="active"),
    ]
    result = metrics.portfolio(DummyData(projects), status_filter="ideas")
    assert result.total == 2


def test_portfolio_tier_filter():
    config = AppConfig()
    metrics = MetricsService(config)
    projects = [
        _make_project(id="local:a", name="a", tier="S"),
        _make_project(id="local:b", name="b", tier="C"),
    ]
    result = metrics.portfolio(DummyData(projects), tier_filter="S")
    assert result.total == 1
    assert result.rows[0].tier == "S"


def test_portfolio_sort_by_name():
    config = AppConfig()
    metrics = MetricsService(config)
    projects = [
        _make_project(id="local:z", name="zebra", tier="A"),
        _make_project(id="local:a", name="alpha", tier="A"),
    ]
    result = metrics.portfolio(DummyData(projects), sort_mode="name")
    assert result.rows[0].name == "alpha"
    assert result.rows[1].name == "zebra"


def test_portfolio_divergence_stale_flagship():
    config = AppConfig()
    metrics = MetricsService(config)
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    projects = [
        _make_project(id="local:a", name="a", tier="S", last_commit_at=old),
    ]
    result = metrics.portfolio(DummyData(projects))
    assert result.rows[0].divergence_signal == "stale-flagship"
    assert result.stale_flagships == 1
    assert result.divergence_count == 1


def test_portfolio_divergence_overactive_low_tier():
    config = AppConfig()
    metrics = MetricsService(config)
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    projects = [
        _make_project(id="local:a", name="a", tier="D", last_commit_at=recent),
    ]
    result = metrics.portfolio(DummyData(projects))
    assert result.rows[0].divergence_signal == "overactive-low-tier"


def test_portfolio_divergence_unproven_flagship():
    config = AppConfig()
    metrics = MetricsService(config)
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    projects = [
        _make_project(id="local:a", name="a", tier="S", last_commit_at=recent),
    ]
    result = metrics.portfolio(DummyData(projects))
    assert result.rows[0].divergence_signal == "unproven-flagship"


def test_portfolio_no_divergence():
    config = AppConfig()
    metrics = MetricsService(config)
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    projects = [
        _make_project(
            id="local:a",
            name="a",
            tier="S",
            has_readme=True,
            has_tests=True,
            has_ci=True,
            last_commit_at=recent,
        ),
    ]
    result = metrics.portfolio(DummyData(projects))
    assert result.rows[0].divergence_signal == ""
    assert result.divergence_count == 0


def test_portfolio_relative_time_labels():
    config = AppConfig()
    metrics = MetricsService(config)
    now = datetime.now(timezone.utc)
    projects = [
        _make_project(id="local:a", name="a", last_commit_at=(now - timedelta(hours=2)).isoformat()),
        _make_project(id="local:b", name="b", last_commit_at=(now - timedelta(days=5)).isoformat()),
        _make_project(id="local:c", name="c", last_commit_at=(now - timedelta(days=60)).isoformat()),
        _make_project(id="local:d", name="d"),  # no commit
    ]
    result = metrics.portfolio(DummyData(projects), sort_mode="name")
    labels = {r.name: r.last_commit_label for r in result.rows}
    assert "h ago" in labels["a"]
    assert "d ago" in labels["b"]
    assert "mo ago" in labels["c"]
    assert labels["d"] == "never"
