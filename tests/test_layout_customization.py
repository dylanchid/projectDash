from __future__ import annotations

import json
from pathlib import Path

from textual.widgets import Static

from projectdash.layout import LayoutStore, PageLayout
from projectdash.views.dashboard import DashboardView
from projectdash.views.customizable import CustomizableView, SectionSpec


def test_layout_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / ".projectdash" / "layouts.json"
    store = LayoutStore(path=path)
    layout = PageLayout(section_ids=("a", "b"), widths={"a": 44, "b": 50})

    store.save_page_layout("dash", layout)

    loaded = store.load_page_layout("dash", ("a",))
    assert loaded.section_ids == ("a", "b")
    assert loaded.width_for("a") == 44
    assert loaded.width_for("b") == 50


def test_layout_store_filters_invalid_payload(tmp_path: Path) -> None:
    path = tmp_path / ".projectdash" / "layouts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "dashboard": {
                    "section_ids": ["missing", "good", "", 7],
                    "widths": {"good": "10", "missing": 2000, "bad": "x"},
                }
            }
        ),
        encoding="utf-8",
    )
    store = LayoutStore(path=path)

    loaded = store.load_page_layout("dashboard", ("good", "other"))

    assert loaded.section_ids == ("good", "missing")
    assert loaded.width_for("good") == 20
    assert loaded.width_for("missing") == 140


def test_dashboard_layout_actions_persist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    view = DashboardView()

    ok, message = view.set_layout_edit_mode(True)
    assert ok is True
    assert "enabled" in message

    ok, _ = view.resize_selected_section(6)
    assert ok is True

    ok, _ = view.move_selected_section(1)
    assert ok is True

    ok, _ = view.add_section("charts")
    assert ok is False

    ok, _ = view.remove_selected_section()
    assert ok is True

    view.apply_layout_preset(("project-explorer", "charts", "project-detail"), widths={"charts": 55})

    store = LayoutStore(path=tmp_path / ".projectdash" / "layouts.json")
    loaded = store.load_page_layout("dashboard", ())
    assert loaded.section_ids == ("project-explorer", "charts", "project-detail")
    assert loaded.width_for("charts") == 55


def test_customizable_view_refreshes_content_after_recompose(monkeypatch) -> None:
    class _DemoView(CustomizableView):
        PAGE_LAYOUT_ID = "demo"

        def __init__(self) -> None:
            super().__init__()
            self.refresh_calls = 0

        def section_specs(self) -> tuple[SectionSpec, ...]:
            return (SectionSpec(section_id="one", title="One", factory=lambda: Static("one")),)

        def refresh_view(self) -> None:
            self.refresh_calls += 1

    view = _DemoView()
    monkeypatch.setattr(view, "refresh", lambda *args, **kwargs: None)
    monkeypatch.setattr(view, "call_after_refresh", lambda callback: callback())

    view.set_layout_edit_mode(True)

    assert view.refresh_calls == 1
