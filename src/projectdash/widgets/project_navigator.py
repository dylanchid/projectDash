from textual.widgets import Static
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.app import ComposeResult
from textual import events
from rich.text import Text
from projectdash.services.metrics import ProjectCardMetric


class ProjectNavigatorSelected(Message):
    """Posted when a project is selected in the navigator."""

    def __init__(self, project_id: str, project_name: str) -> None:
        super().__init__()
        self.project_id = project_id
        self.project_name = project_name


class NavigatorCard(Static):
    """A single project card in the navigator carousel."""

    can_focus = True

    def __init__(self, metric: ProjectCardMetric, selected: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.metric = metric
        self.selected = selected

    def on_click(self, event: events.Click) -> None:  # type: ignore[override]
        self.post_message(ProjectNavigatorSelected(self.metric.project_id, self.metric.name))

    def on_key(self, event: events.Key) -> None:
        """Handle Enter key on focused card."""
        if event.key == "enter":
            self.post_message(ProjectNavigatorSelected(self.metric.project_id, self.metric.name))

    def render(self):
        title_style = "bold #ffffff" if self.selected else "bold #aaaaaa"
        meta_style = "#666666" if self.selected else "#555555"

        risk_pct = int((self.metric.blocked / max(1, self.metric.total)) * 100)
        risk_symbol = "!!" if risk_pct >= 30 else "!" if risk_pct >= 15 else "·"

        return Text.assemble(
            (f"{self.metric.name[:12].upper()}\n", title_style),
            (f"{self.metric.total} | {self.metric.active} | {risk_symbol}\n", meta_style),
            (f"OK" if risk_pct < 15 else f"Risk {risk_pct}%", meta_style),
        )


class ProjectNavigator(Static):
    """Horizontal carousel showing projects in 2 rows."""

    def __init__(self, project_cards: list[ProjectCardMetric] | None = None, selected_id: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.project_cards = project_cards or []
        self.selected_id = selected_id
        self._selection_index = 0
        self._row1: Horizontal | None = None
        self._row2: Horizontal | None = None

    def compose(self) -> ComposeResult:
        """Render 2 rows of project cards."""
        self._row1 = Horizontal(classes="nav-row")
        self._row2 = Horizontal(classes="nav-row")
        yield self._row1
        yield self._row2

    def on_mount(self) -> None:
        """Called when widget is mounted - update with initial data."""
        self._render_cards()

    def update_cards(self, project_cards: list[ProjectCardMetric], selected_id: str | None = None) -> None:
        """Update the carousel with new project cards and optionally select one."""
        self.project_cards = project_cards
        if selected_id:
            self.selected_id = selected_id

        # Try to maintain selection index if same card count
        if self.selected_id and project_cards:
            for i, card in enumerate(project_cards):
                if card.project_id == self.selected_id:
                    self._selection_index = i
                    break
            else:
                # Selected card no longer exists, select first
                self.selected_id = project_cards[0].project_id if project_cards else None
                self._selection_index = 0
        elif project_cards:
            self.selected_id = project_cards[0].project_id
            self._selection_index = 0

        # Render after widget is mounted
        if self.is_mounted:
            self._render_cards()
        else:
            self.call_after_refresh(self._render_cards)

    def _render_cards(self) -> None:
        """Rebuild the carousel with current project cards."""
        if self._row1 is None or self._row2 is None:
            return

        try:
            # Clear existing cards
            self._row1.remove_children()
            self._row2.remove_children()
        except Exception:
            pass

        if not self.project_cards:
            try:
                self._row1.mount(Static("No projects loaded.", classes="placeholder-text"))
            except Exception:
                pass
            return

        # Split cards into 2 rows: 5 cards per row
        cards_per_row = 5
        row1_cards = self.project_cards[:cards_per_row]
        row2_cards = self.project_cards[cards_per_row : cards_per_row * 2]

        try:
            # Row 1
            for card_metric in row1_cards:
                is_selected = card_metric.project_id == self.selected_id
                nav_card = NavigatorCard(
                    card_metric,
                    selected=is_selected,
                    classes="nav-card" + (" is-selected" if is_selected else "")
                )
                self._row1.mount(nav_card)

            # Row 2
            for card_metric in row2_cards:
                is_selected = card_metric.project_id == self.selected_id
                nav_card = NavigatorCard(
                    card_metric,
                    selected=is_selected,
                    classes="nav-card" + (" is-selected" if is_selected else "")
                )
                self._row2.mount(nav_card)
        except Exception as e:
            print(f"Error rendering navigator cards: {e}")

    def select_next(self, delta: int = 1) -> str | None:
        """Navigate carousel by delta positions. Returns selected project_id or None."""
        if not self.project_cards:
            return None

        self._selection_index = (self._selection_index + delta) % len(self.project_cards)
        self.selected_id = self.project_cards[self._selection_index].project_id

        if self.is_mounted:
            self._render_cards()
        return self.selected_id

    def select_by_id(self, project_id: str) -> bool:
        """Select a project by ID. Returns True if found."""
        for i, card in enumerate(self.project_cards):
            if card.project_id == project_id:
                self._selection_index = i
                self.selected_id = project_id
                if self.is_mounted:
                    self._render_cards()
                return True
        return False

    def on_project_navigator_selected(self, message: ProjectNavigatorSelected) -> None:
        """Handle card click selection."""
        self.select_by_id(message.project_id)
        self.post_message(message)
