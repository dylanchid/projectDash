from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static

class ConfirmationScreen(ModalScreen[bool]):
    def __init__(self, message: str, title: str = "Confirm Action"):
        super().__init__()
        self.message = message
        self.title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="confirmation-dialog"):
            yield Static(self.title, id="confirmation-title")
            yield Static(self.message, id="confirmation-message")
            with Horizontal(id="confirmation-buttons"):
                yield Button("Cancel", id="cancel", variant="default")
                yield Button("Confirm", id="confirm", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)
