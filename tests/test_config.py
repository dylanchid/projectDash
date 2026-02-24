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
