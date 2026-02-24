from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _dev_command() -> list[str]:
    return [sys.executable, "-m", "projectdash.app"]


def _start_process(root: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(_dev_command(), cwd=root)


def main() -> int:
    try:
        from watchfiles import watch
    except ImportError:
        print("watchfiles is not installed. Run: uv sync --group dev")
        return 1

    root = _project_root()
    process = _start_process(root)
    print("Running ProjectDash dev mode with auto-restart...")
    print("Press Ctrl+C to stop.")

    try:
        for changes in watch(str(root / "src")):
            if not _is_relevant_change(root, changes):
                continue
            _stop_process(process)
            process = _start_process(root)
    except KeyboardInterrupt:
        pass
    finally:
        _stop_process(process)
    return 0


def _is_relevant_change(root: Path, changes: set[tuple[object, str]]) -> bool:
    for _, changed_path in changes:
        path = Path(changed_path)
        if path.suffix not in {".py", ".tcss"}:
            continue
        try:
            relative = path.resolve().relative_to(root)
        except Exception:
            continue
        if relative.parts and relative.parts[0] == "src":
            return True
    return False


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
