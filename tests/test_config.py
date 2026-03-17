from pathlib import Path

from projectdash.config import AppConfig


def test_config_merge_file_json(tmp_path: Path) -> None:
    config_file = tmp_path / "projectdash.config.json"
    config_file.write_text(
        """
{
  "kanban_statuses": ["Backlog", "In Progress", "Done"],
  "linear_status_mappings": {"In Progress": "state-2"},
  "sprint_overflow_column_label": "Unmapped",
  "default_user_capacity_points": 14,
  "workload_bar_width": 12,
  "sprint_risk_blocked_threshold": 2,
  "sprint_risk_failing_pr_threshold": 3,
  "sprint_risk_stale_review_days": 5,
  "sprint_risk_stale_review_threshold": 4,
  "sprint_risk_overloaded_owners_threshold": 2,
  "sprint_risk_overloaded_utilization_pct": 85,
  "seed_mock_data": true,
  "user_capacity_overrides": {"alice": 16}
}
""".strip(),
        encoding="utf-8",
    )

    merged = AppConfig().merge_file(config_file)
    assert merged.kanban_statuses == ("Backlog", "In Progress", "Done")
    assert merged.linear_status_mappings == {"in progress": "state-2"}
    assert merged.sprint_overflow_column_label == "Unmapped"
    assert merged.default_user_capacity_points == 14
    assert merged.workload_bar_width == 12
    assert merged.sprint_risk_blocked_threshold == 2
    assert merged.sprint_risk_failing_pr_threshold == 3
    assert merged.sprint_risk_stale_review_days == 5
    assert merged.sprint_risk_stale_review_threshold == 4
    assert merged.sprint_risk_overloaded_owners_threshold == 2
    assert merged.sprint_risk_overloaded_utilization_pct == 85
    assert merged.seed_mock_data is True
    assert merged.user_capacity_overrides["alice"] == 16
    assert merged.config_source == str(config_file)


def test_config_merge_file_invalid_json_falls_back(tmp_path: Path) -> None:
    config_file = tmp_path / "projectdash.config.json"
    config_file.write_text("{ this-is: bad json", encoding="utf-8")

    defaults = AppConfig()
    merged = defaults.merge_file(config_file)
    assert merged == defaults


def test_config_from_env_parses_mock_seed_flag(monkeypatch) -> None:
    monkeypatch.setenv("PD_ENABLE_MOCK_SEED", "true")
    monkeypatch.setenv("PD_CONFIG_PATH", "non-existent-config-file.json")
    config = AppConfig.from_env()
    assert config.seed_mock_data is True


def test_config_from_env_parses_github_settings(monkeypatch) -> None:
    monkeypatch.setenv("PD_GITHUB_REPOS", "acme/platform, acme/web")
    monkeypatch.setenv("PD_GITHUB_PR_LIMIT", "15")
    monkeypatch.setenv("PD_GITHUB_SYNC_CHECKS", "false")
    monkeypatch.setenv("PD_CONFIG_PATH", "non-existent-config-file.json")

    config = AppConfig.from_env()

    assert config.github_repositories == ("acme/platform", "acme/web")
    assert config.github_pr_limit == 15
    assert config.github_sync_checks is False


def test_config_from_env_parses_sprint_risk_thresholds(monkeypatch) -> None:
    monkeypatch.setenv("PD_SPRINT_RISK_BLOCKED_THRESHOLD", "2")
    monkeypatch.setenv("PD_SPRINT_RISK_FAILING_PR_THRESHOLD", "3")
    monkeypatch.setenv("PD_SPRINT_RISK_STALE_REVIEW_DAYS", "6")
    monkeypatch.setenv("PD_SPRINT_RISK_STALE_REVIEW_THRESHOLD", "4")
    monkeypatch.setenv("PD_SPRINT_RISK_OVERLOADED_OWNERS_THRESHOLD", "2")
    monkeypatch.setenv("PD_SPRINT_RISK_OVERLOADED_UTIL_PCT", "90")
    monkeypatch.setenv("PD_CONFIG_PATH", "non-existent-config-file.json")

    config = AppConfig.from_env()

    assert config.sprint_risk_blocked_threshold == 2
    assert config.sprint_risk_failing_pr_threshold == 3
    assert config.sprint_risk_stale_review_days == 6
    assert config.sprint_risk_stale_review_threshold == 4
    assert config.sprint_risk_overloaded_owners_threshold == 2
    assert config.sprint_risk_overloaded_utilization_pct == 90
