from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from textual.message import Message


class TriageFilterChips(Horizontal):
    """A horizontal container of triage filter chips."""

    DEFAULT_CSS = """
    TriageFilterChips {
        height: 1;
        margin: 0 2 1 2;
        padding: 0;
        background: transparent;
        color: #666666;
    }

    .triage-chip {
        background: #1a1a1a;
        color: #666666;
        padding: 0 1;
        margin-right: 1;
        text-style: none;
    }

    .triage-chip.is-active {
        background: #333333;
        color: #ffffff;
        text-style: bold;
    }

    #triage-chips-label {
        color: #555555;
        margin-right: 1;
        text-style: bold;
    }
    """

    class Toggled(Message):
        """Sent when a chip is toggled."""
        def __init__(self, filter_name: str) -> None:
            self.filter_name = filter_name
            super().__init__()

    def __init__(self, filters: dict[str, bool], **kwargs) -> None:
        super().__init__(**kwargs)
        self.filters = filters

    def compose(self) -> ComposeResult:
        yield Static("TRIAGE:", id="triage-chips-label")
        for name, active in self.filters.items():
            classes = "triage-chip is-active" if active else "triage-chip"
            yield Static(name.upper(), id=f"triage-chip-{name}", classes=classes)

    def update_filters(self, filters: dict[str, bool]) -> None:
        self.filters = filters
        for name, active in filters.items():
            try:
                chip = self.query_one(f"#triage-chip-{name}", Static)
                if active:
                    chip.add_class("is-active")
                else:
                    chip.remove_class("is-active")
            except Exception:
                pass
