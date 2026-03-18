from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from projectdash.models import LocalProject


def compute_activity_score(project: LocalProject) -> int:
    score = 0
    if project.has_readme:
        score += 20
    if project.has_tests:
        score += 30
    if project.has_ci:
        score += 20
    if project.last_commit_at:
        try:
            commit_dt = datetime.fromisoformat(project.last_commit_at)
            if commit_dt.tzinfo is None:
                commit_dt = commit_dt.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - commit_dt).days
            if age_days < 7:
                score += 30
            elif age_days < 30:
                score += 20
            elif age_days < 90:
                score += 10
        except (ValueError, TypeError):
            pass
    return score


class PortfolioScanner:

    def scan_root(self, root: Path) -> list[LocalProject]:
        if not root.is_dir():
            return []
        projects: list[LocalProject] = []
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if not self._is_git_repo(entry):
                continue
            last_commit = self._read_last_commit(entry)
            has_readme, has_tests, has_ci = self._detect_indicators(entry)
            project = LocalProject(
                id=f"local:{entry.name}",
                name=entry.name,
                path=str(entry),
                last_commit_at=last_commit,
                has_readme=has_readme,
                has_tests=has_tests,
                has_ci=has_ci,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            projects.append(project)
        return projects

    def load_manifest(self, manifest_path: Path) -> dict[str, dict]:
        if not manifest_path.exists():
            return {}
        text = manifest_path.read_text(encoding="utf-8")
        suffix = manifest_path.suffix.lower()
        if suffix in (".yml", ".yaml"):
            try:
                import yaml  # type: ignore

                parsed = yaml.safe_load(text)
                return parsed if isinstance(parsed, dict) else {}
            except ImportError:
                return {}
            except Exception:
                return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, Exception):
            return {}

    def save_manifest(self, manifest_path: Path, data: dict[str, dict]) -> None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        suffix = manifest_path.suffix.lower()
        if suffix in (".yml", ".yaml"):
            try:
                import yaml  # type: ignore

                manifest_path.write_text(
                    yaml.dump(data, default_flow_style=False, sort_keys=True),
                    encoding="utf-8",
                )
                return
            except ImportError:
                pass
        manifest_path.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )

    def apply_manifest(
        self, projects: list[LocalProject], manifest: dict[str, dict]
    ) -> list[LocalProject]:
        result: list[LocalProject] = []
        for project in projects:
            overrides = manifest.get(project.id, {})
            if not isinstance(overrides, dict):
                result.append(project)
                continue
            merged = LocalProject(
                id=project.id,
                name=project.name,
                path=project.path,
                status=str(overrides.get("status", project.status)),
                tier=str(overrides.get("tier", project.tier)),
                type=str(overrides.get("type", project.type)),
                tags=list(overrides.get("tags", project.tags)),
                description=overrides.get("description", project.description),
                last_commit_at=project.last_commit_at,
                has_readme=project.has_readme,
                has_tests=project.has_tests,
                has_ci=project.has_ci,
                linked_linear_id=overrides.get(
                    "linked_linear_id", project.linked_linear_id
                ),
                linked_repo=overrides.get("linked_repo", project.linked_repo),
                created_at=project.created_at,
            )
            result.append(merged)
        return result

    def _is_git_repo(self, path: Path) -> bool:
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--git-dir"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def _read_last_commit(self, path: Path) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "log", "-1", "--format=%cI"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return None
        except (subprocess.TimeoutExpired, OSError):
            return None

    def _detect_indicators(self, path: Path) -> tuple[bool, bool, bool]:
        has_readme = (path / "README.md").exists() or (path / "README.rst").exists()
        has_tests = (
            (path / "tests").is_dir()
            or (path / "test").is_dir()
            or (path / "spec").is_dir()
            or any(path.glob("test_*.py"))
        )
        has_ci = (path / ".github" / "workflows").is_dir() or (
            path / ".circleci"
        ).is_dir()
        return has_readme, has_tests, has_ci
