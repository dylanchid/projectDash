from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SectionLayout:
    section_id: str
    width: int | None = None


@dataclass(frozen=True)
class PageLayout:
    section_ids: tuple[str, ...]
    widths: dict[str, int]

    def width_for(self, section_id: str, default: int | None = None) -> int | None:
        value = self.widths.get(section_id)
        if value is None:
            return default
        return value


class LayoutStore:
    """Persist per-page layout customizations under .projectdash/layouts.json."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (Path.cwd() / ".projectdash" / "layouts.json")

    def load_page_layout(self, page_id: str, default_section_ids: tuple[str, ...]) -> PageLayout:
        payload = self._read()
        raw = payload.get(page_id)
        if not isinstance(raw, dict):
            return PageLayout(section_ids=default_section_ids, widths={})

        raw_section_ids = raw.get("section_ids")
        raw_widths = raw.get("widths")

        section_ids = [section_id for section_id in default_section_ids if section_id in self._to_str_tuple(raw_section_ids)]
        for section_id in self._to_str_tuple(raw_section_ids):
            if section_id not in section_ids:
                section_ids.append(section_id)

        normalized_widths: dict[str, int] = {}
        if isinstance(raw_widths, dict):
            for key, value in raw_widths.items():
                if not isinstance(key, str):
                    continue
                try:
                    width = int(value)
                except (TypeError, ValueError):
                    continue
                normalized_widths[key] = max(20, min(width, 140))

        return PageLayout(section_ids=tuple(section_ids) or default_section_ids, widths=normalized_widths)

    def save_page_layout(self, page_id: str, layout: PageLayout) -> None:
        payload = self._read()
        payload[page_id] = {
            "section_ids": list(layout.section_ids),
            "widths": dict(layout.widths),
        }
        self._write(payload)

    def _read(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {str(key): value for key, value in parsed.items() if isinstance(value, dict)}

    def _write(self, payload: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _to_str_tuple(value: object) -> tuple[str, ...]:
        if isinstance(value, (list, tuple)):
            return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
        return ()
