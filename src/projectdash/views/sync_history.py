from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static


class SyncHistoryScreen(Screen):
    BINDINGS = [
        ("j", "history_down", "Down"),
        ("k", "history_up", "Up"),
        ("enter", "open_selected", "Open Details"),
        ("/", "start_filter", "Filter"),
        ("escape", "close_screen", "Close"),
        ("q", "close_screen", "Close"),
        ("h", "close_screen", "Close"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.selected_index = 0
        self.expanded_indices: set[int] = set()
        self.filter_query = ""
        self.filter_active = False

    def compose(self) -> ComposeResult:
        yield Static("SYNC HISTORY", id="sync-history-modal-header")
        yield Static("ENTRIES", classes="section-label")
        yield Static("", id="sync-history-modal-content")

    def on_mount(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        entries = self._filtered_entries(self.app.data_manager.get_sync_history(limit=200), self.filter_query)
        if not entries:
            body = "No sync history found."
        else:
            self.selected_index = max(0, min(self.selected_index, len(entries) - 1))
            detail_lines: list[str] = []
            if self.filter_active:
                detail_lines.append(f"Filter: {self.filter_query}_")
                detail_lines.append("")
            elif self.filter_query:
                detail_lines.append(f"Filter: {self.filter_query}")
                detail_lines.append("")
            for idx, entry in enumerate(entries):
                is_selected = idx == self.selected_index
                marker = ">" if is_selected else " "
                detail_lines.append(
                    f"{marker} {entry.get('created_at', '?')} | {entry.get('result', '?')} | {entry.get('summary', '')}"
                )
                if idx in self.expanded_indices:
                    diagnostics = entry.get("diagnostics") or {}
                    if diagnostics:
                        for step, status in diagnostics.items():
                            detail_lines.append(f"    - {step}: {status}")
                    else:
                        detail_lines.append("    - no diagnostics")
                    hints = self._entry_recovery_hints(entry)
                    if hints:
                        detail_lines.append("    - recovery hints:")
                        for hint in hints:
                            detail_lines.append(f"      * {hint}")
                    detail_lines.append("")
            body = "\n".join(detail_lines).rstrip()
        self.query_one("#sync-history-modal-content", Static).update(body)

    def action_history_down(self) -> None:
        entries = self._filtered_entries(self.app.data_manager.get_sync_history(limit=200), self.filter_query)
        if not entries:
            return
        self.selected_index = (self.selected_index + 1) % len(entries)
        self.refresh_view()

    def action_history_up(self) -> None:
        entries = self._filtered_entries(self.app.data_manager.get_sync_history(limit=200), self.filter_query)
        if not entries:
            return
        self.selected_index = (self.selected_index - 1) % len(entries)
        self.refresh_view()

    def action_open_selected(self) -> None:
        entries = self._filtered_entries(self.app.data_manager.get_sync_history(limit=200), self.filter_query)
        if not entries:
            return
        if self.selected_index not in self.expanded_indices:
            self.expanded_indices.add(self.selected_index)
        self.refresh_view()

    def action_start_filter(self) -> None:
        self.filter_active = True
        self.refresh_view()

    def action_close_screen(self) -> None:
        if self.filter_active:
            self.filter_active = False
            self.filter_query = ""
            self.selected_index = 0
            self.refresh_view()
            return
        if self.selected_index in self.expanded_indices:
            self.expanded_indices.remove(self.selected_index)
            self.refresh_view()
            return
        self.app.pop_screen()

    def on_key(self, event) -> None:  # type: ignore[override]
        if not self.filter_active:
            return
        handled = True
        if event.key == "enter":
            self.filter_active = False
        elif event.key == "backspace":
            self.filter_query = self.filter_query[:-1]
            self.selected_index = 0
        elif event.key == "escape":
            self.filter_active = False
            self.filter_query = ""
            self.selected_index = 0
        elif event.key == "space":
            self.filter_query += " "
            self.selected_index = 0
        elif event.character and event.character.isprintable():
            self.filter_query += event.character
            self.selected_index = 0
        else:
            handled = False
        if handled:
            self.refresh_view()
            event.stop()

    @staticmethod
    def _entry_search_blob(entry: dict) -> str:
        diagnostics = entry.get("diagnostics") or {}
        diagnostics_text = " ".join(f"{k} {v}" for k, v in diagnostics.items())
        parts = [
            str(entry.get("created_at", "")),
            str(entry.get("result", "")),
            str(entry.get("summary", "")),
            diagnostics_text,
        ]
        return " ".join(parts).casefold()

    @classmethod
    def _filtered_entries(cls, entries: list[dict], query: str) -> list[dict]:
        normalized = query.strip().casefold()
        if not normalized:
            return entries
        return [entry for entry in entries if normalized in cls._entry_search_blob(entry)]

    @staticmethod
    def _entry_recovery_hints(entry: dict) -> list[str]:
        diagnostics = entry.get("diagnostics") or {}
        blob = " ".join(
            [
                str(entry.get("summary", "")),
                *(f"{key} {value}" for key, value in diagnostics.items()),
            ]
        ).casefold()

        hints: list[str] = []
        if "linear_api_key not set" in blob:
            hints.append("Set LINEAR_API_KEY, then run `pd sync`.")
        if "github_token not set" in blob:
            hints.append("Set GITHUB_TOKEN, then run `pd sync-github`.")
        if "no repositories configured" in blob:
            hints.append("Configure PD_GITHUB_REPOS as owner/repo values.")
        if "rate limit" in blob:
            hints.append("Retry after provider rate-limit window.")
        if "auth failed" in blob or "unauthorized" in blob:
            hints.append("Verify token scopes and connector credentials.")
        if "persist failed" in blob or "reload failed" in blob:
            hints.append("Check local DB write permissions and disk space.")
        if not hints and ("failed" in blob or "error" in blob):
            hints.append("Open diagnostics, fix connector config, then retry sync.")
        return hints
