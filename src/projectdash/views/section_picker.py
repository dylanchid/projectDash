from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static


class SectionPickerScreen(Screen[str | None]):
    BINDINGS = [
        ("j", "move_down", "Down"),
        ("k", "move_up", "Up"),
        ("enter", "select_section", "Add Section"),
        ("escape", "close_screen", "Close"),
        ("q", "close_screen", "Close"),
    ]

    def __init__(self, options: list[tuple[str, str]]) -> None:
        super().__init__()
        self._options = options
        self._selected_index = 0

    def compose(self) -> ComposeResult:
        yield Static("ADD SECTION", id="section-picker-header")
        yield Static("AVAILABLE", classes="section-label")
        yield Static("", id="section-picker-body")

    def on_mount(self) -> None:
        self._refresh()

    def action_move_down(self) -> None:
        if not self._options:
            return
        self._selected_index = (self._selected_index + 1) % len(self._options)
        self._refresh()

    def action_move_up(self) -> None:
        if not self._options:
            return
        self._selected_index = (self._selected_index - 1) % len(self._options)
        self._refresh()

    def action_select_section(self) -> None:
        if not self._options:
            self.dismiss(None)
            return
        self.dismiss(self._options[self._selected_index][0])

    def action_close_screen(self) -> None:
        self.dismiss(None)

    def _refresh(self) -> None:
        body = self.query_one("#section-picker-body", Static)
        if not self._options:
            body.update("No additional sections available.")
            return
        lines = []
        for index, (_section_id, label) in enumerate(self._options):
            marker = ">" if index == self._selected_index else " "
            lines.append(f"{marker} {label}")
        body.update("\n".join(lines))
