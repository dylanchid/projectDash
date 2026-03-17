from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_project_env() -> None:
    """Load .env from cwd and repo root so CLI/TUI work from any launch path."""
    cwd_env = Path.cwd() / ".env"
    repo_env = Path(__file__).resolve().parents[2] / ".env"

    seen: set[Path] = set()
    for candidate in (cwd_env, repo_env):
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.exists():
            load_dotenv(dotenv_path=candidate, override=False)
