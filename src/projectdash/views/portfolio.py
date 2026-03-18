from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from projectdash.services.metrics import PortfolioMetricSet, PortfolioRowMetric

if TYPE_CHECKING:
    from projectdash.app import ProjectDash


class PortfolioView(Static):
    """Top-level portfolio gallery of all local projects."""

    VISUAL_MODES = ("all", "active", "paused", "shipped", "ideas")
    SORT_MODES = ("tier", "score", "commit", "name")
    TIER_VALUES = ("S", "A", "B", "C", "D")
    TIER_FILTER_CYCLE = ("all", "S", "A", "B", "C", "D")
    STATUS_VALUES = ("idea", "exploration", "active", "paused", "shipped", "archived")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.visual_mode = "all"
        self.sort_mode = "tier"
        self.tier_filter = "all"
        self.project_scope_id: str | None = None
        self.selected_project_id: str | None = None
        self._project_order: list[str] = []
        self.detail_open = False

    def on_mount(self) -> None:
        self.refresh_view()

    def on_show(self) -> None:
        self.refresh_view()

    def compose(self) -> ComposeResult:
        with Horizontal(id="portfolio-layout"):
            with Vertical(id="portfolio-main"):
                yield Static("PORTFOLIO GALLERY", id="view-header")
                yield Static("", id="portfolio-toolbar")
                yield Static("", id="portfolio-content", classes="placeholder-text")
            with Vertical(id="portfolio-sidebar", classes="detail-sidebar"):
                yield Static("PROJECT DETAIL", classes="detail-sidebar-title")
                yield Static("", id="portfolio-detail")
                yield Static("", id="portfolio-hint", classes="detail-sidebar-hint")

    def refresh_view(self) -> None:
        metric_set = self.app.metrics.portfolio(
            self.app.data_manager,
            status_filter=self.visual_mode,
            tier_filter=self.tier_filter,
            sort_mode=self.sort_mode,
        )
        self._project_order = [row.project_id for row in metric_set.rows]

        if self.selected_project_id and self.selected_project_id not in self._project_order:
            self.selected_project_id = None
        if self.selected_project_id is None and self._project_order:
            self.selected_project_id = self._project_order[0]

        self.query_one("#portfolio-toolbar", Static).update(self._toolbar_text(metric_set))
        self.query_one("#portfolio-content", Static).update(self._content_text(metric_set))
        self._refresh_detail_panel(metric_set)

    def set_project_scope(self, project_id: str | None) -> None:
        pass

    def move_selection(self, delta: int) -> None:
        if not self._project_order:
            return
        if self.selected_project_id not in self._project_order:
            self.selected_project_id = self._project_order[0]
        else:
            idx = self._project_order.index(self.selected_project_id)
            self.selected_project_id = self._project_order[(idx + delta) % len(self._project_order)]
        self.refresh_view()

    def page_selection(self, delta_pages: int) -> None:
        self.move_selection(delta_pages * 10)

    def toggle_visual_mode(self) -> tuple[bool, str]:
        idx = self.VISUAL_MODES.index(self.visual_mode)
        self.visual_mode = self.VISUAL_MODES[(idx + 1) % len(self.VISUAL_MODES)]
        self.refresh_view()
        return True, f"Portfolio filter: {self.visual_mode}"

    def toggle_graph_density(self) -> tuple[bool, str]:
        idx = self.SORT_MODES.index(self.sort_mode)
        self.sort_mode = self.SORT_MODES[(idx + 1) % len(self.SORT_MODES)]
        self.refresh_view()
        return True, f"Portfolio sort: {self.sort_mode}"

    def cycle_tier_filter(self) -> tuple[bool, str]:
        idx = self.TIER_FILTER_CYCLE.index(self.tier_filter) if self.tier_filter in self.TIER_FILTER_CYCLE else 0
        self.tier_filter = self.TIER_FILTER_CYCLE[(idx + 1) % len(self.TIER_FILTER_CYCLE)]
        self.refresh_view()
        return True, f"Portfolio tier filter: {self.tier_filter}"

    def open_primary(self) -> tuple[bool, str]:
        row = self._selected_row()
        if not row:
            return False, "No project selected"
        editor = os.getenv("EDITOR", "code")
        if not shutil.which(editor):
            return False, f"Editor not found: {editor}"
        try:
            subprocess.Popen(
                [editor, row.path],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, f"Opened {row.name} in {editor}"
        except Exception as e:
            return False, f"Failed to open editor: {e}"

    def open_secondary(self) -> tuple[bool, str]:
        row = self._selected_row()
        if not row or not row.linked_repo:
            return False, "No linked GitHub repo"
        import webbrowser

        url = f"https://github.com/{row.linked_repo}"
        try:
            webbrowser.open_new_tab(url)
            return True, f"Opened {row.linked_repo}"
        except Exception as e:
            return False, f"Failed to open URL: {e}"

    def copy_primary(self) -> tuple[bool, str]:
        row = self._selected_row()
        if not row:
            return False, "No project selected"

        def _copy(value: str) -> bool:
            for cmd in (
                ["pbcopy"],
                ["wl-copy"],
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
            ):
                if shutil.which(cmd[0]):
                    try:
                        subprocess.run(cmd, input=value, text=True, check=True)
                        return True
                    except Exception:
                        pass
            return False

        if _copy(row.path):
            return True, f"Copied path: {row.path}"
        return False, "Clipboard tool not found"

    def jump_context(self) -> tuple[bool, str]:
        row = self._selected_row()
        if not row:
            return False, "No project selected"
        if not row.linked_linear_id:
            return False, f"{row.name} has no linked Linear project"
        self.app._set_project_scope(row.linked_linear_id)
        self.app.action_switch_tab("sprint")
        return True, f"Scoped to {row.name}"

    def open_detail(self) -> None:
        self.detail_open = True
        self.refresh_view()

    def close_detail(self) -> None:
        self.detail_open = False
        self.refresh_view()

    def cycle_tier(self) -> tuple[bool, str]:
        row = self._selected_row()
        if not row:
            return False, "No project selected"
        idx = self.TIER_VALUES.index(row.tier) if row.tier in self.TIER_VALUES else 0
        new_tier = self.TIER_VALUES[(idx + 1) % len(self.TIER_VALUES)]
        self.app.run_worker(
            self.app.data_manager.update_local_project_field(row.project_id, "tier", new_tier),
            exclusive=False,
        )
        for p in self.app.data_manager.local_projects:
            if p.id == row.project_id:
                p.tier = new_tier
                break
        self.refresh_view()
        return True, f"{row.name} tier: {row.tier} -> {new_tier}"

    def cycle_status(self) -> tuple[bool, str]:
        row = self._selected_row()
        if not row:
            return False, "No project selected"
        idx = self.STATUS_VALUES.index(row.status) if row.status in self.STATUS_VALUES else 0
        new_status = self.STATUS_VALUES[(idx + 1) % len(self.STATUS_VALUES)]
        self.app.run_worker(
            self.app.data_manager.update_local_project_field(row.project_id, "status", new_status),
            exclusive=False,
        )
        for p in self.app.data_manager.local_projects:
            if p.id == row.project_id:
                p.status = new_status
                break
        self.refresh_view()
        return True, f"{row.name} status: {row.status} -> {new_status}"

    def context_summary(self) -> dict[str, str]:
        return {
            "mode": self.visual_mode,
            "sort": self.sort_mode,
            "tier": self.tier_filter,
            "selected": self.selected_project_id or "none",
        }

    def capture_filter_state(self) -> dict[str, object]:
        return {
            "visual_mode": self.visual_mode,
            "sort_mode": self.sort_mode,
            "tier_filter": self.tier_filter,
            "selected_project_id": self.selected_project_id,
            "detail_open": self.detail_open,
        }

    def restore_filter_state(self, state: dict[str, object] | None) -> None:
        if not state:
            return
        self.visual_mode = str(state.get("visual_mode") or self.visual_mode)
        self.sort_mode = str(state.get("sort_mode") or self.sort_mode)
        self.tier_filter = str(state.get("tier_filter") or self.tier_filter)
        self.selected_project_id = str(state.get("selected_project_id") or "") or None
        self.detail_open = bool(state.get("detail_open", self.detail_open))
        self.refresh_view()

    def preferred_project_id(self) -> str | None:
        row = self._selected_row()
        if row and row.linked_linear_id:
            return row.linked_linear_id
        return None

    # --- private ---

    @staticmethod
    def _score_bar(score: int) -> str:
        filled = min(5, score // 20)
        return "\u2588" * filled + "\u2591" * (5 - filled)

    def _selected_row(self) -> PortfolioRowMetric | None:
        if not self.selected_project_id:
            return None
        metric_set = self.app.metrics.portfolio(
            self.app.data_manager,
            status_filter=self.visual_mode,
            tier_filter=self.tier_filter,
            sort_mode=self.sort_mode,
        )
        for row in metric_set.rows:
            if row.project_id == self.selected_project_id:
                return row
        return None

    def _toolbar_text(self, metric_set: PortfolioMetricSet) -> Text:
        text = Text()
        text.append(
            f"{metric_set.total} projects  |  "
            f"status:{self.visual_mode}  |  tier:{self.tier_filter}  |  "
            f"sort:{self.sort_mode}  |  "
            f"active:{metric_set.active_count}",
            style="#cfcfcf",
        )
        if metric_set.divergence_count > 0:
            text.append(f"  |  divergence:{metric_set.divergence_count}", style="#ff8888")
        if metric_set.stale_flagships > 0:
            text.append(f"  |  stale-flagships:{metric_set.stale_flagships}", style="#ff8888")
        if metric_set.tier_distribution:
            dist_parts = [
                f"{t}:{metric_set.tier_distribution[t]}"
                for t in ("S", "A", "B", "C", "D")
                if t in metric_set.tier_distribution
            ]
            if dist_parts:
                text.append(f"  |  {' '.join(dist_parts)}", style="#888888")
        text.append("\n")
        text.append("V filter  S tier-filter  g sort  e tier  m status  ] drill  o open", style="#5f5f5f")
        return text

    def _content_text(self, metric_set: PortfolioMetricSet) -> Text:
        text = Text()
        text.append(
            "Tier  Name                 Type         Status       Commit     Indicators\n",
            style="bold #666666",
        )
        text.append(
            "--------------------------------------------------------------------------\n",
            style="#333333",
        )

        if not metric_set.rows:
            text.append(
                "No projects found. Set PD_PORTFOLIO_ROOT to scan.\n",
                style="#666666",
            )
            return text

        visible, start, end = self._windowed_rows(metric_set.rows)
        for row in visible:
            marker = ">" if row.project_id == self.selected_project_id else " "
            style = self._row_style(row)
            indicators = self._indicators_text(row)
            text.append(
                f"{marker} [{row.tier}]  "
                f"{row.name[:20].ljust(20)} "
                f"{row.type[:12].ljust(12)} "
                f"{row.status[:12].ljust(12)} "
                f"{row.last_commit_label[:10].ljust(10)} "
                f"{indicators}\n",
                style=style,
            )

        if len(metric_set.rows) > len(visible):
            text.append(
                f"\nShowing {start + 1}-{end} of {metric_set.total} (PgUp/PgDn page)\n",
                style="#666666",
            )
        return text

    _TIER_COLORS = {
        "S": "#ffee88",
        "A": "#aaffaa",
        "B": "#ffffff",
        "C": "#a0a0a0",
        "D": "#666666",
    }

    def _row_style(self, row: PortfolioRowMetric) -> str:
        # Signal colors take priority (same for selected and unselected)
        if row.divergence_signal == "stale-flagship":
            prefix = "bold " if row.project_id == self.selected_project_id else ""
            return f"{prefix}#ff8888"
        if row.divergence_signal == "overactive-low-tier":
            prefix = "bold " if row.project_id == self.selected_project_id else ""
            return f"{prefix}#88ff88"
        if row.divergence_signal == "unproven-flagship":
            prefix = "bold " if row.project_id == self.selected_project_id else ""
            return f"{prefix}#ffff88"
        color = self._TIER_COLORS.get(row.tier, "#a0a0a0")
        if row.project_id == self.selected_project_id:
            return f"bold {color}"
        return color

    def _indicators_text(self, row: PortfolioRowMetric) -> str:
        parts: list[str] = []
        if row.has_readme:
            parts.append("README")
        if row.has_tests:
            parts.append("TESTS")
        if row.has_ci:
            parts.append("CI")
        if row.divergence_signal:
            label = row.divergence_signal.upper().replace("-", " ")
            parts.append(f"[{label}]")
        return " ".join(parts) if parts else "-"

    def _refresh_detail_panel(self, metric_set: PortfolioMetricSet) -> None:
        detail = self.query_one("#portfolio-detail", Static)
        hint = self.query_one("#portfolio-hint", Static)

        row = None
        for r in metric_set.rows:
            if r.project_id == self.selected_project_id:
                row = r
                break

        if not row:
            detail.update("No project selected.")
            hint.update("j/k select  v filter  g sort")
            return

        home = os.path.expanduser("~")
        display_path = row.path.replace(home, "~") if row.path.startswith(home) else row.path

        score_bar = self._score_bar(row.activity_score)
        lines = [
            row.name,
            "-" * 35,
            f"Path:    {display_path}",
            f"Type:    {row.type.ljust(14)}  Tier: {row.tier}",
            f"Status:  {row.status}",
            f"Score:   {score_bar}  {row.activity_score}/100",
            f"Last:    {row.last_commit_label}",
            "",
        ]

        if row.description:
            lines.append(f"Desc:    {row.description}")
            lines.append("")

        if row.tags:
            lines.append(f"Tags:    {', '.join(row.tags)}")
            lines.append("")

        indicator_parts: list[str] = []
        if row.has_readme:
            indicator_parts.append("README")
        if row.has_tests:
            indicator_parts.append("TESTS")
        if row.has_ci:
            indicator_parts.append("CI")
        lines.append(f"Indicators:  {' '.join(indicator_parts) or 'none'}")

        if row.divergence_signal:
            lines.append("")
            lines.append(f"Signal: {row.divergence_signal}")

        if row.linked_linear_id:
            lines.append("")
            lines.append(f"Linear:  linked ({row.linked_linear_id[:12]})")
        if row.linked_repo:
            lines.append(f"GitHub:  {row.linked_repo}")

        lines.append("")
        lines.append("-" * 35)
        lines.append("o   open in editor")
        if row.linked_repo:
            lines.append("O   open GitHub")
        if row.linked_linear_id:
            lines.append("]   drill into sprint board")
        lines.append("e   cycle tier")
        lines.append("m   cycle status")
        lines.append("b   copy path")

        detail.update("\n".join(lines))
        hint.update("o open  O github  ] drill  e tier  m status  b copy")

    def _windowed_rows(
        self, rows: list[PortfolioRowMetric]
    ) -> tuple[list[PortfolioRowMetric], int, int]:
        total = len(rows)
        if total == 0:
            return [], 0, 0
        page_size = 20
        selected_index = 0
        if self.selected_project_id:
            for index, row in enumerate(rows):
                if row.project_id == self.selected_project_id:
                    selected_index = index
                    break
        start = (selected_index // page_size) * page_size
        end = min(total, start + page_size)
        return rows[start:end], start, end
