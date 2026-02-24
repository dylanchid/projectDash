from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _to_int(value: Any, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass(frozen=True)
class AppConfig:
    kanban_statuses: tuple[str, ...] = ("Todo", "In Progress", "Review", "Done")
    linear_status_mappings: dict[str, str] = field(default_factory=dict)
    sprint_overflow_column_label: str = "Other"
    active_statuses: tuple[str, ...] = ("In Progress", "Review")
    done_statuses: tuple[str, ...] = ("Done",)
    default_user_capacity_points: int = 10
    workload_warning_pct: int = 70
    workload_critical_pct: int = 80
    workload_bar_width: int = 10
    workload_issue_preview_limit: int = 3
    timeline_horizon_days: int = 30
    timeline_max_projects: int = 6
    seed_mock_data: bool = False
    user_capacity_overrides: dict[str, int] = field(default_factory=dict)
    config_source: str = "defaults/env"

    @classmethod
    def from_env(cls) -> "AppConfig":
        config = cls(
            default_user_capacity_points=max(1, _get_int_env("PD_DEFAULT_CAPACITY_POINTS", 10)),
            workload_warning_pct=max(1, _get_int_env("PD_WORKLOAD_WARNING_PCT", 70)),
            workload_critical_pct=max(1, _get_int_env("PD_WORKLOAD_CRITICAL_PCT", 80)),
            workload_bar_width=max(5, _get_int_env("PD_WORKLOAD_BAR_WIDTH", 10)),
            workload_issue_preview_limit=max(1, _get_int_env("PD_WORKLOAD_ISSUE_PREVIEW_LIMIT", 3)),
            timeline_horizon_days=max(7, _get_int_env("PD_TIMELINE_HORIZON_DAYS", 30)),
            timeline_max_projects=max(1, _get_int_env("PD_TIMELINE_MAX_PROJECTS", 6)),
            seed_mock_data=_to_bool(os.getenv("PD_ENABLE_MOCK_SEED"), False),
        )
        config_path = os.getenv("PD_CONFIG_PATH", "projectdash.config.json")
        return config.merge_file(Path(config_path))

    def merge_file(self, path: Path) -> "AppConfig":
        if not path.exists():
            return self
        loaded = self._load_config_file(path)
        if not loaded:
            return self
        merged = dict(self.__dict__)
        for key in merged:
            if key in loaded:
                merged[key] = loaded[key]
        merged["kanban_statuses"] = tuple(str(v) for v in merged["kanban_statuses"])
        if not isinstance(merged["linear_status_mappings"], dict):
            merged["linear_status_mappings"] = {}
        else:
            merged["linear_status_mappings"] = {
                str(key).strip().casefold(): str(value).strip()
                for key, value in merged["linear_status_mappings"].items()
                if str(key).strip() and str(value).strip()
            }
        merged["sprint_overflow_column_label"] = str(merged["sprint_overflow_column_label"]).strip() or "Other"
        merged["active_statuses"] = tuple(str(v) for v in merged["active_statuses"])
        merged["done_statuses"] = tuple(str(v) for v in merged["done_statuses"])
        merged["default_user_capacity_points"] = _to_int(
            merged["default_user_capacity_points"], self.default_user_capacity_points, 1
        )
        merged["workload_warning_pct"] = _to_int(
            merged["workload_warning_pct"], self.workload_warning_pct, 1
        )
        merged["workload_critical_pct"] = _to_int(
            merged["workload_critical_pct"], self.workload_critical_pct, 1
        )
        merged["workload_bar_width"] = _to_int(
            merged["workload_bar_width"], self.workload_bar_width, 5
        )
        merged["workload_issue_preview_limit"] = _to_int(
            merged["workload_issue_preview_limit"], self.workload_issue_preview_limit, 1
        )
        merged["timeline_horizon_days"] = _to_int(
            merged["timeline_horizon_days"], self.timeline_horizon_days, 7
        )
        merged["timeline_max_projects"] = _to_int(
            merged["timeline_max_projects"], self.timeline_max_projects, 1
        )
        merged["seed_mock_data"] = _to_bool(merged["seed_mock_data"], self.seed_mock_data)
        if not isinstance(merged["user_capacity_overrides"], dict):
            merged["user_capacity_overrides"] = {}
        else:
            merged["user_capacity_overrides"] = {
                str(key): _to_int(value, self.default_user_capacity_points, 1)
                for key, value in merged["user_capacity_overrides"].items()
            }
        merged["config_source"] = str(path)
        return AppConfig(**merged)

    def _load_config_file(self, path: Path) -> dict[str, Any]:
        suffix = path.suffix.lower()
        text = path.read_text(encoding="utf-8")
        if suffix == ".json":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        if suffix in {".yml", ".yaml"}:
            try:
                import yaml  # type: ignore
            except ImportError:
                return {}
            try:
                parsed = yaml.safe_load(text)
            except Exception:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}
