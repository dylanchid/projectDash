from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Static

from projectdash.layout import LayoutStore, PageLayout


SectionFactory = Callable[[], Widget]


@dataclass(frozen=True)
class SectionSpec:
    section_id: str
    title: str
    factory: SectionFactory
    default_width: int = 36
    min_width: int = 20
    max_width: int = 140
    removable: bool = True


class CustomizableView(Static):
    PAGE_LAYOUT_ID = ""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._layout_store = LayoutStore()
        self._layout_edit_mode = False
        self._selected_section_index = 0

    def section_specs(self) -> tuple[SectionSpec, ...]:
        raise NotImplementedError

    def layout_container_id(self) -> str:
        return f"{self.PAGE_LAYOUT_ID}-layout"

    def compose(self) -> ComposeResult:
        layout = self._current_layout()
        with Horizontal(id=self.layout_container_id()):
            for section_id in layout.section_ids:
                spec = self._spec_by_id(section_id)
                if spec is None:
                    continue
                section_widget = spec.factory()
                width = layout.width_for(section_id, spec.default_width)
                if width is not None:
                    section_widget.styles.width = width
                section_widget.add_class("customizable-section")
                if self._layout_edit_mode and self._selected_section_id() == section_id:
                    section_widget.add_class("is-layout-selected")
                yield section_widget

    def layout_edit_mode(self) -> bool:
        return self._layout_edit_mode

    def set_layout_edit_mode(self, enabled: bool) -> tuple[bool, str]:
        self._layout_edit_mode = enabled
        if self._selected_section_index >= len(self._current_layout().section_ids):
            self._selected_section_index = max(0, len(self._current_layout().section_ids) - 1)
        self._recompose_with_data_refresh()
        return True, f"Layout edit {'enabled' if enabled else 'disabled'}"

    def cycle_selected_section(self, delta: int) -> tuple[bool, str]:
        section_ids = self._current_layout().section_ids
        if not section_ids:
            return False, "No sections available"
        self._selected_section_index = (self._selected_section_index + delta) % len(section_ids)
        self._recompose_with_data_refresh()
        selected = self._selected_section_id() or "none"
        return True, f"Selected section: {selected}"

    def move_selected_section(self, delta: int) -> tuple[bool, str]:
        section_ids = list(self._current_layout().section_ids)
        if len(section_ids) < 2:
            return False, "Need at least two sections to reorder"
        current = self._selected_section_index % len(section_ids)
        target = max(0, min(len(section_ids) - 1, current + delta))
        if current == target:
            return False, "Section already at edge"
        section_ids[current], section_ids[target] = section_ids[target], section_ids[current]
        self._selected_section_index = target
        layout = PageLayout(section_ids=tuple(section_ids), widths=dict(self._current_layout().widths))
        self._save_layout(layout)
        self._recompose_with_data_refresh()
        return True, "Section reordered"

    def resize_selected_section(self, delta: int) -> tuple[bool, str]:
        section_id = self._selected_section_id()
        if section_id is None:
            return False, "No section selected"
        spec = self._spec_by_id(section_id)
        if spec is None:
            return False, "Unknown section"
        layout = self._current_layout()
        base = layout.width_for(section_id, spec.default_width) or spec.default_width
        width = max(spec.min_width, min(spec.max_width, base + delta))
        widths = dict(layout.widths)
        widths[section_id] = width
        self._save_layout(PageLayout(section_ids=layout.section_ids, widths=widths))
        self._recompose_with_data_refresh()
        return True, f"{section_id} width: {width}"

    def add_section(self, section_id: str) -> tuple[bool, str]:
        spec = self._spec_by_id(section_id)
        if spec is None:
            return False, f"Unknown section: {section_id}"
        section_ids = list(self._current_layout().section_ids)
        if section_id in section_ids:
            return False, f"Section already visible: {section_id}"
        section_ids.append(section_id)
        self._selected_section_index = len(section_ids) - 1
        self._save_layout(PageLayout(section_ids=tuple(section_ids), widths=dict(self._current_layout().widths)))
        self._recompose_with_data_refresh()
        return True, f"Added section: {section_id}"

    def remove_selected_section(self) -> tuple[bool, str]:
        section_id = self._selected_section_id()
        if section_id is None:
            return False, "No section selected"
        spec = self._spec_by_id(section_id)
        if spec is None:
            return False, "Unknown section"
        if not spec.removable:
            return False, f"Section is locked: {section_id}"
        section_ids = [item for item in self._current_layout().section_ids if item != section_id]
        if not section_ids:
            return False, "At least one section must remain"
        self._selected_section_index = max(0, min(self._selected_section_index, len(section_ids) - 1))
        widths = dict(self._current_layout().widths)
        widths.pop(section_id, None)
        self._save_layout(PageLayout(section_ids=tuple(section_ids), widths=widths))
        self._recompose_with_data_refresh()
        return True, f"Removed section: {section_id}"

    def available_sections_to_add(self) -> list[SectionSpec]:
        present = set(self._current_layout().section_ids)
        return [spec for spec in self.section_specs() if spec.section_id not in present]

    def apply_layout_preset(self, section_ids: tuple[str, ...], widths: dict[str, int] | None = None) -> None:
        filtered = []
        for section_id in section_ids:
            if self._spec_by_id(section_id) is None:
                continue
            if section_id in filtered:
                continue
            filtered.append(section_id)
        if not filtered:
            filtered = [spec.section_id for spec in self.section_specs()[:1]]
        normalized_widths: dict[str, int] = {}
        for section_id, width in (widths or {}).items():
            spec = self._spec_by_id(section_id)
            if spec is None:
                continue
            normalized_widths[section_id] = max(spec.min_width, min(spec.max_width, int(width)))
        self._selected_section_index = 0
        self._save_layout(PageLayout(section_ids=tuple(filtered), widths=normalized_widths))
        self._recompose_with_data_refresh()

    def selected_section_label(self) -> str:
        section_id = self._selected_section_id()
        spec = self._spec_by_id(section_id) if section_id else None
        return spec.title if spec else "none"

    def default_section_ids(self) -> tuple[str, ...]:
        return tuple(spec.section_id for spec in self.section_specs())

    def _selected_section_id(self) -> str | None:
        section_ids = self._current_layout().section_ids
        if not section_ids:
            return None
        return section_ids[self._selected_section_index % len(section_ids)]

    def _current_layout(self) -> PageLayout:
        return self._layout_store.load_page_layout(self.PAGE_LAYOUT_ID, self.default_section_ids())

    def _save_layout(self, layout: PageLayout) -> None:
        self._layout_store.save_page_layout(self.PAGE_LAYOUT_ID, layout)

    def _recompose_with_data_refresh(self) -> None:
        self.refresh(recompose=True)
        try:
            self.call_after_refresh(self._safe_refresh_view)
        except Exception:
            self._safe_refresh_view()

    def _safe_refresh_view(self) -> None:
        refresh_view = getattr(self, "refresh_view", None)
        if refresh_view is None:
            return
        try:
            refresh_view()
        except Exception:
            return

    def _spec_by_id(self, section_id: str | None) -> SectionSpec | None:
        if not section_id:
            return None
        for spec in self.section_specs():
            if spec.section_id == section_id:
                return spec
        return None
