from __future__ import annotations

from dataclasses import dataclass
from textwrap import fill

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from projectdash.charts import LineChartRenderer, LineChartSpec, LineSeries

try:
    from textual_plotext import PlotextPlot
except Exception:
    PlotextPlot = None


@dataclass(frozen=True)
class IdeationCard:
    idea_id: str
    title: str
    category: str
    value: str
    chart_kind: str
    action_hint: str
    chart_spec_id: str | None = None


class IdeationGalleryView(Static):
    VISUAL_MODES = ("all", "delivery", "flow", "quality", "capacity", "portfolio")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.visual_mode = "all"
        self.graph_density = "detailed"
        self.project_scope_id: str | None = None
        self.selected_idea_id: str | None = None
        self.detail_open = False
        self._idea_order: list[str] = []

        self._line_renderer = LineChartRenderer()
        self._line_render_style = "classic"
        self._line_window_start = 0
        self._line_window_size = 12
        self._line_selected_series = 0

    def on_mount(self) -> None:
        self.refresh_view()

    def on_show(self) -> None:
        self.refresh_view()

    def compose(self) -> ComposeResult:
        with Horizontal(id="ideation-layout"):
            with Vertical(id="ideation-main"):
                yield Static("IDEATION CHART LAB", id="view-header")
                yield Static("", id="ideation-toolbar")
                with Horizontal(id="ideation-grid"):
                    yield Vertical(id="ideation-col-left", classes="ideation-column")
                    yield Vertical(id="ideation-col-right", classes="ideation-column")
            with Vertical(id="ideation-sidebar", classes="detail-sidebar"):
                yield Static("CONCEPT DETAIL", classes="detail-sidebar-title")
                yield Static("", id="ideation-detail")
                yield Static("", id="ideation-hint", classes="detail-sidebar-hint")

    def refresh_view(self) -> None:
        cards = self._visible_cards()
        self._idea_order = [card.idea_id for card in cards]
        if self.selected_idea_id not in self._idea_order:
            self.selected_idea_id = self._idea_order[0] if self._idea_order else None
            self._line_window_start = 0
            self._line_selected_series = 0
        self._clamp_line_window(cards)

        self.query_one("#ideation-toolbar", Static).update(self._toolbar_text(cards))
        visible_cards, start, end = self._windowed_cards(cards)
        mid = (len(visible_cards) + 1) // 2
        left_cards = visible_cards[:mid]
        right_cards = visible_cards[mid:]

        left_col = self.query_one("#ideation-col-left", Vertical)
        right_col = self.query_one("#ideation-col-right", Vertical)
        left_col.remove_children()
        right_col.remove_children()

        if self._plotext_enabled():
            self._mount_plot_cards(left_col, left_cards, start + 1)
            self._mount_plot_cards(right_col, right_cards, start + 1 + len(left_cards))
        else:
            self._mount_text_cards(left_col, left_cards, start + 1)
            self._mount_text_cards(right_col, right_cards, start + 1 + len(left_cards))

        if len(cards) > len(visible_cards):
            footer = Static(
                f"Showing {start + 1}-{end + 1} of {len(cards)}  |  PgUp/PgDn for more",
                classes="placeholder-text",
            )
            left_col.mount(footer)

        self._refresh_detail_panel(cards)

    def set_project_scope(self, project_id: str | None) -> None:
        self.project_scope_id = project_id
        self.refresh_view()

    def move_selection(self, delta: int) -> None:
        if not self._idea_order:
            return
        if self.selected_idea_id not in self._idea_order:
            self.selected_idea_id = self._idea_order[0]
            self._line_window_start = 0
            self._line_selected_series = 0
            self.refresh_view()
            return
        current_index = self._idea_order.index(self.selected_idea_id)
        next_index = (current_index + delta) % len(self._idea_order)
        self.selected_idea_id = self._idea_order[next_index]
        self._line_window_start = 0
        self._line_selected_series = 0
        self.refresh_view()

    def page_selection(self, delta_pages: int) -> None:
        if delta_pages == 0:
            return
        jump = 6 if self.graph_density == "detailed" else 4
        self.move_selection(delta_pages * jump)

    def toggle_visual_mode(self) -> tuple[bool, str]:
        current_index = self.VISUAL_MODES.index(self.visual_mode)
        self.visual_mode = self.VISUAL_MODES[(current_index + 1) % len(self.VISUAL_MODES)]
        self.refresh_view()
        return True, f"Ideation category: {self.visual_mode}"

    def toggle_graph_density(self) -> tuple[bool, str]:
        self.graph_density = "compact" if self.graph_density == "detailed" else "detailed"
        self._line_window_size = 8 if self.graph_density == "compact" else 12
        self.refresh_view()
        return True, f"Ideation density: {self.graph_density}"

    def open_primary(self) -> tuple[bool, str]:
        card = self._selected_card()
        if not card:
            return False, "No concept selected"
        # For now, just a placeholder
        return True, f"Concept focused: {card.title}"

    def open_secondary(self) -> tuple[bool, str]:
        return False, "No secondary action for chart lab"

    def copy_primary(self) -> tuple[bool, str]:
        card = self._selected_card()
        if not card:
            return False, "No concept selected"
        
        def _copy(value: str) -> bool:
            import shutil, subprocess
            for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
                if shutil.which(cmd[0]):
                    try:
                        subprocess.run(cmd, input=value, text=True, check=True)
                        return True
                    except Exception:
                        pass
            return False

        if _copy(card.idea_id):
            return True, f"Copied concept ID: {card.idea_id}"
        return False, "Clipboard tool not found"

    def jump_context(self) -> tuple[bool, str]:
        return False, "No jump context for chart lab"

    def open_detail(self) -> None:
        if self.selected_idea_id is None and self._idea_order:
            self.selected_idea_id = self._idea_order[0]
        self.detail_open = True
        self.refresh_view()

    def close_detail(self) -> None:
        self.detail_open = False
        self.refresh_view()

    def adjust_line_pan(self, delta: int) -> tuple[bool, str]:
        card = self._selected_card()
        spec = self._selected_line_spec()
        if card is None or spec is None:
            return False, "Line pan works on line-chart concepts only"
        max_start = max(0, len(spec.x_labels) - self._line_window_size)
        self._line_window_start = max(0, min(max_start, self._line_window_start + delta))
        self.refresh_view()
        return True, f"{card.title}: pan {self._line_window_start + 1}-{self._line_window_start + self._line_window_size}"

    def adjust_line_zoom(self, delta: int) -> tuple[bool, str]:
        card = self._selected_card()
        spec = self._selected_line_spec()
        if card is None or spec is None:
            return False, "Line zoom works on line-chart concepts only"
        next_size = self._line_window_size - delta
        next_size = max(5, min(len(spec.x_labels), next_size))
        self._line_window_size = next_size
        self._clamp_line_window(self._visible_cards())
        self.refresh_view()
        return True, f"{card.title}: zoom window {self._line_window_size}"

    def cycle_line_series(self, delta: int) -> tuple[bool, str]:
        card = self._selected_card()
        spec = self._selected_line_spec()
        if card is None or spec is None:
            return False, "Series cycling works on line-chart concepts only"
        self._line_selected_series = (self._line_selected_series + delta) % len(spec.series)
        selected = spec.series[self._line_selected_series]
        self.refresh_view()
        return True, f"{card.title}: focus series {selected.name}"

    def cycle_line_render_style(self) -> tuple[bool, str]:
        self._line_render_style = "hires" if self._line_render_style == "classic" else "classic"
        self.refresh_view()
        return True, f"Line renderer: {self._line_render_style}"

    def context_summary(self) -> dict[str, str]:
        focus = self.selected_idea_id or "none"
        spec = self._selected_line_spec()
        filter_label = "chart-lab"
        if spec is not None:
            selected = spec.series[self._line_selected_series % len(spec.series)]
            filter_label = (
                f"chart-lab line:{selected.name} "
                f"window:{self._line_window_start + 1}-{self._line_window_start + self._line_window_size}"
            )
        return {
            "mode": self.visual_mode,
            "density": self.graph_density,
            "filter": f"{filter_label} style:{self._line_render_style}",
            "selected": focus,
        }

    def capture_filter_state(self) -> dict[str, object]:
        return {
            "visual_mode": self.visual_mode,
            "graph_density": self.graph_density,
            "selected_idea_id": self.selected_idea_id,
            "detail_open": self.detail_open,
            "line_window_start": self._line_window_start,
            "line_window_size": self._line_window_size,
            "line_selected_series": self._line_selected_series,
            "line_render_style": self._line_render_style,
        }

    def restore_filter_state(self, state: dict[str, object] | None) -> None:
        if not state:
            return
        self.visual_mode = str(state.get("visual_mode") or self.visual_mode)
        self.graph_density = str(state.get("graph_density") or self.graph_density)
        self.selected_idea_id = str(state.get("selected_idea_id") or "") or None
        self.detail_open = bool(state.get("detail_open", self.detail_open))
        self._line_window_start = int(state.get("line_window_start", self._line_window_start))
        self._line_window_size = int(state.get("line_window_size", self._line_window_size))
        self._line_selected_series = int(state.get("line_selected_series", self._line_selected_series))
        style = str(state.get("line_render_style") or self._line_render_style)
        if style in {"classic", "hires"}:
            self._line_render_style = style
        self.refresh_view()

    def _plotext_enabled(self) -> bool:
        return PlotextPlot is not None

    def _toolbar_text(self, cards: list[IdeationCard]) -> Text:
        by_category: dict[str, int] = {}
        for card in cards:
            by_category[card.category] = by_category.get(card.category, 0) + 1
        total = len(self._all_cards())
        breakdown = "  ".join(f"{name}:{count}" for name, count in sorted(by_category.items()))
        plot_backend = "plotext" if self._plotext_enabled() else "native"
        text = Text()
        text.append(
            f"{len(cards)}/{total} concepts  |  cat:{self.visual_mode}  |  density:{self.graph_density}  |  "
            f"style:{self._line_render_style}  |  backend:{plot_backend}  |  controls: j/k  9/0  +/-  ;/'  7\n",
            style="#cfcfcf",
        )
        if self._freshness_enabled():
            text.append(f"{self._freshness_text()}\n", style="#7e7e7e")
        text.append(f"{breakdown or 'none'}", style="#5f5f5f")
        return text

    def _freshness_text(self) -> str:
        return self.app.data_manager.freshness_summary_line(("linear", "github"))

    def _freshness_enabled(self) -> bool:
        return bool(getattr(self.app, "sync_freshness_visible", True))

    def _visible_cards(self) -> list[IdeationCard]:
        cards = self._all_cards()
        if self.visual_mode == "all":
            return cards
        return [card for card in cards if card.category == self.visual_mode]

    def _windowed_cards(self, cards: list[IdeationCard]) -> tuple[list[IdeationCard], int, int]:
        if not cards:
            return [], -1, -1
        page_size = 8 if self.graph_density == "detailed" else 6
        if page_size >= len(cards):
            return cards, 0, len(cards) - 1
        selected_id = self.selected_idea_id if self.selected_idea_id in {card.idea_id for card in cards} else cards[0].idea_id
        selected_index = 0
        for index, card in enumerate(cards):
            if card.idea_id == selected_id:
                selected_index = index
                break
        half = page_size // 2
        start = max(0, min(len(cards) - page_size, selected_index - half))
        end = start + page_size - 1
        return cards[start : end + 1], start, end

    def _mount_text_cards(self, container: Vertical, cards: list[IdeationCard], start_index: int) -> None:
        for index, card in enumerate(cards, start=start_index):
            container.mount(Static(self._card_block_text(card, index), classes="ideation-card-text"))

    def _mount_plot_cards(self, container: Vertical, cards: list[IdeationCard], start_index: int) -> None:
        for index, card in enumerate(cards, start=start_index):
            card_box = Vertical(classes="ideation-card")
            selected = card.idea_id == self.selected_idea_id
            marker = ">" if selected else " "
            title_style = "bold #ffffff" if selected else "bold #a8a8a8"
            card_box.mount(Static(Text.assemble((f"{marker} [{index:02}] {card.title}", title_style)), classes="ideation-card-title"))
            card_box.mount(Static(self._wrap(card.value, 44), classes="ideation-card-value"))
            spec = self._line_spec(card)
            if spec is not None:
                plot_widget = PlotextPlot(classes="ideation-plot")
                card_box.mount(plot_widget)
                self._draw_plotext_line(plot_widget, spec)
            else:
                card_box.mount(Static(self._non_line_preview(card.chart_kind), classes="ideation-card-fallback"))
            card_box.mount(Static(f"cue: {self._wrap(card.action_hint, 38)}", classes="ideation-card-cue"))
            container.mount(card_box)

    def _draw_plotext_line(self, widget, spec: LineChartSpec) -> None:
        plt = widget.plt
        self._safe_call(plt, ["clear_data"])
        self._safe_call(plt, ["clear_figure"])
        self._safe_call(plt, ["clf"])
        self._safe_call(plt, ["theme"], "pro")
        self._safe_call(plt, ["canvas_color"], "default")
        self._safe_call(plt, ["axes_color"], 240)
        self._safe_call(plt, ["ticks_color"], 248)
        self._safe_call(plt, ["ticks_style"], "dim")
        plot_height = 12 if self.graph_density == "detailed" else 10
        self._safe_call(plt, ["plotsize", "plot_size"], 44, plot_height)

        labels = spec.x_labels[self._line_window_start : self._line_window_start + self._line_window_size]
        if not labels:
            return
        series_values = [
            series.values[self._line_window_start : self._line_window_start + self._line_window_size]
            for series in spec.series
        ]
        x = list(range(len(labels)))
        palette = ["cyan+", "green+", "orange+", "magenta+", "blue+", "yellow"]

        for series_index, series in enumerate(spec.series):
            values = series_values[series_index]
            if not values:
                continue
            focused = series_index == self._line_selected_series
            marker = "braille" if focused and self._line_render_style == "hires" else ("hd" if focused else "dot")
            color = palette[series_index % len(palette)]
            style = "bold" if focused else "dim"
            self._safe_call(plt, ["plot"], x, values, label=series.name, marker=marker, color=color, style=style)

        if spec.threshold is not None:
            self._safe_call(plt, ["horizontal_line", "hline"], spec.threshold, color=245)

        if spec.annotations:
            window_end = self._line_window_start + len(labels) - 1
            for index in sorted(spec.annotations.keys()):
                if self._line_window_start <= index <= window_end:
                    self._safe_call(plt, ["vertical_line", "vline"], index - self._line_window_start, color=238)

        step = 1 if len(x) <= 8 else 2
        tick_positions = list(range(0, len(x), step))
        if tick_positions and tick_positions[-1] != x[-1]:
            tick_positions.append(x[-1])
        tick_labels = [labels[pos] for pos in tick_positions]

        focused = spec.series[self._line_selected_series % len(spec.series)].name
        self._safe_call(plt, ["title"], spec.title)
        self._safe_call(plt, ["xticks"], tick_positions, tick_labels)
        self._safe_call(plt, ["xfrequency"], max(1, min(6, len(tick_positions))))
        self._safe_call(plt, ["yfrequency"], 4)
        self._safe_call(plt, ["xlabel"], f"{labels[0]} -> {labels[-1]}")
        self._safe_call(plt, ["ylabel"], focused)
        self._safe_call(plt, ["frame"], True)
        self._safe_call(plt, ["xaxes"], True, False)
        self._safe_call(plt, ["yaxes"], True, False)
        self._safe_call(plt, ["grid"], True, False)

    def _safe_call(self, plt, names: list[str], *args, **kwargs) -> bool:
        for name in names:
            fn = getattr(plt, name, None)
            if fn is None:
                continue
            try:
                fn(*args, **kwargs)
                return True
            except Exception:
                continue
        return False

    def _card_block_text(self, card: IdeationCard, index: int) -> Text:
        text = Text()
        selected = card.idea_id == self.selected_idea_id
        marker = ">" if selected else " "
        header_style = "bold #ffffff" if selected else "bold #b0b0b0"
        text.append(f"{marker} [{index:02}] {card.title}\n", style=header_style)
        text.append(f"   {self._wrap(card.value, width=42, indent='')}\n", style="#a9a9a9")
        text.append(f"   {card.chart_kind} · {card.category}\n", style="#7f7f7f")
        text.append(self._chart_preview(card, selected), style="#f3f3f3")
        text.append(f"   cue: {self._wrap(card.action_hint, width=37, indent='')}\n", style="#8f8f8f")
        text.append("   " + ("─" * 52) + "\n", style="#2f2f2f")
        return text

    def _chart_preview(self, card: IdeationCard, selected: bool) -> str:
        spec = self._line_spec(card)
        if spec is not None:
            window_size = self._line_window_size
            if self._line_render_style == "hires":
                return (
                    self._line_renderer.render_hires(
                        spec,
                        selected_series_index=self._line_selected_series,
                        window_start=self._line_window_start,
                        window_size=window_size,
                        cell_rows=3 if selected else 2,
                    )
                    + "\n"
                )
            if selected or self.graph_density == "detailed":
                return (
                    self._line_renderer.render_detailed(
                        spec,
                        selected_series_index=self._line_selected_series,
                        window_start=self._line_window_start,
                        window_size=window_size,
                        height=9 if selected else 7,
                    )
                    + "\n"
                )
            return (
                self._line_renderer.render_compact(
                    spec,
                    selected_series_index=self._line_selected_series,
                    window_start=self._line_window_start,
                    window_size=min(window_size, 8),
                )
                + "\n"
            )
        return self._non_line_preview(card.chart_kind)

    def _non_line_preview(self, chart_kind: str) -> str:
        samples = {
            "control": "p50 2.1d  p85 4.8d  p95 7.2d\nin-control ▂▂▃▄▃▂\nbreach · · ! ! · ·",
            "aging": "0-3d   ███████████████ 18\n4-7d   ████████       9\n8-14d  █████          6\n15d+   ██             2",
            "heatmap": "     Mon Tue Wed Thu Fri\nAPI  ░░  ▒▒  ▓▓  ██  ▓▓\nWeb  ░░  ░░  ▒▒  ▓▓  ██",
            "funnel": "Draft 34 -> Review 25\nReview 25 -> QA 17\nQA 17 -> Merge 12",
            "radar": "Flake:7 Retry:5 Timeout:4\nQueue:3 Infra:6 Schema:2",
            "stacked": "Alex [Done██████][Act███][Blk█]\nKim  [Done████][Act████][Blk██]",
            "matrix": "     API Web Data ML\nAPI   -   4   2   1\nWeb   3   -   2   0",
            "forecast": "wk1 62% wk2 68% wk3 76%\nwk4 82% wk5 88% wk6 91%",
            "quadrant": "HI/HIGH-RISK: 5\nHI/LOW-RISK : 3\nLOW/HIGH-RISK: 4",
            "calendar": "Jan ░░▒▒▓▓██▓▓▒▒░░\nFeb ░▒▒▓▓███▓▒▒░░",
        }
        return samples.get(chart_kind, "preview pending")

    def _refresh_detail_panel(self, cards: list[IdeationCard]) -> None:
        detail = self.query_one("#ideation-detail", Static)
        hint = self.query_one("#ideation-hint", Static)
        if not self.detail_open or not self.selected_idea_id:
            detail.update(
                "Chart lab focus mode.\n\n"
                f"Category: {self.visual_mode}\n"
                f"Density: {self.graph_density}\n"
                f"Visible concepts: {len(cards)}\n"
                f"Renderer style: {self._line_render_style}\n"
                f"Backend: {'plotext' if self._plotext_enabled() else 'native'}\n\n"
                "Open detail for rationale + implementation steps."
            )
            hint.update("Enter open • Esc close • j/k select • 9/0 pan • +/- zoom • ;/' series • 7 style")
            return

        selected = self._selected_card()
        if selected is None:
            detail.update("Concept not found.")
            hint.update("j/k select • v category • g density")
            return

        line_spec = self._line_spec(selected)
        interaction = "static prototype"
        if line_spec is not None:
            focused = line_spec.series[self._line_selected_series % len(line_spec.series)].name
            interaction = (
                f"interactive line (focus {focused})\n"
                f"window: {self._line_window_start + 1}-{self._line_window_start + self._line_window_size}\n"
                f"style: {self._line_render_style}\n"
                f"backend: {'plotext' if self._plotext_enabled() else 'native'}"
            )
        detail.update(
            f"{selected.title}\n\n"
            f"Category: {selected.category}\n"
            f"Chart: {selected.chart_kind}\n\n"
            f"Intent\n{selected.value}\n\n"
            f"Design Cue\n{selected.action_hint}\n\n"
            f"Interaction\n{interaction}\n\n"
            "Build Next\n"
            "- feed live metrics\n"
            "- wire alert thresholds\n"
            "- enable compare baseline"
        )
        hint.update("Enter open • Esc close • 9/0 pan • +/- zoom • ;/' series • 7 style • v/g")

    def _selected_card(self) -> IdeationCard | None:
        selected_id = self.selected_idea_id
        if selected_id is None:
            return None
        for card in self._visible_cards():
            if card.idea_id == selected_id:
                return card
        return None

    def _selected_line_spec(self) -> LineChartSpec | None:
        card = self._selected_card()
        if card is None:
            return None
        return self._line_spec(card)

    def _line_spec(self, card: IdeationCard) -> LineChartSpec | None:
        specs = self._line_specs()
        if card.chart_spec_id is None:
            return None
        return specs.get(card.chart_spec_id)

    def _line_specs(self) -> dict[str, LineChartSpec]:
        labels = [f"D{i:02}" for i in range(1, 17)]
        return {
            "line-minimal": LineChartSpec(
                title="A. Lead Time Minimal",
                x_labels=labels,
                series=[
                    LineSeries("LeadTime", [3.2, 3.3, 3.5, 3.7, 3.8, 4.1, 4.0, 3.9, 3.8, 3.6, 3.5, 3.4, 3.3, 3.2, 3.1, 3.0]),
                    LineSeries("Target", [3.0] * 16),
                ],
                threshold=3.0,
                annotations={5: "scope jump", 11: "process tune"},
            ),
            "line-analytical": LineChartSpec(
                title="B. Throughput Overlay",
                x_labels=labels,
                series=[
                    LineSeries("Actual", [28, 29, 31, 34, 37, 39, 41, 40, 38, 36, 35, 33, 34, 35, 37, 39]),
                    LineSeries("RollingAvg", [28, 28.5, 29.3, 31.0, 33.0, 35.0, 37.0, 38.5, 38.8, 38.6, 37.8, 36.2, 35.4, 35.1, 35.5, 36.4]),
                    LineSeries("Forecast", [27, 28, 29, 31, 33, 35, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46]),
                ],
                threshold=36.0,
                annotations={4: "incident", 9: "fix merged", 13: "staffing"},
            ),
            "line-story": LineChartSpec(
                title="C. Scope vs Done Story",
                x_labels=labels,
                series=[
                    LineSeries("Scope", [55, 57, 60, 61, 66, 70, 73, 75, 77, 78, 79, 80, 81, 82, 84, 86]),
                    LineSeries("Done", [18, 21, 24, 29, 31, 36, 42, 49, 56, 62, 69, 75, 79, 83, 86, 89]),
                    LineSeries("Confidence", [42, 44, 45, 47, 46, 49, 54, 61, 66, 71, 77, 84, 86, 88, 90, 92]),
                ],
                threshold=70.0,
                annotations={2: "onboarding", 6: "unblock", 10: "RC", 14: "cutover"},
            ),
            "line-failure-rate": LineChartSpec(
                title="D. CI Failure Rate",
                x_labels=labels,
                series=[
                    LineSeries("Fail%", [6.0, 6.2, 6.4, 7.1, 7.8, 8.5, 8.1, 7.4, 6.8, 6.1, 5.8, 5.1, 4.9, 4.6, 4.4, 4.2]),
                    LineSeries("SLO", [5.0] * 16),
                ],
                threshold=5.0,
                annotations={5: "flake burst", 11: "cache fix"},
            ),
            "line-review-latency": LineChartSpec(
                title="E. PR Review Latency",
                x_labels=labels,
                series=[
                    LineSeries("MedianHrs", [11, 12, 13, 14, 16, 18, 17, 15, 14, 13, 12, 11, 10, 10, 9, 9]),
                    LineSeries("P90Hrs", [23, 24, 25, 27, 31, 36, 34, 30, 28, 26, 24, 22, 21, 20, 19, 18]),
                ],
                threshold=16.0,
                annotations={6: "holiday week", 12: "review rota"},
            ),
            "line-capacity-pulse": LineChartSpec(
                title="F. Capacity Pulse",
                x_labels=labels,
                series=[
                    LineSeries("Planned", [62, 63, 65, 66, 67, 69, 70, 70, 71, 72, 73, 74, 75, 75, 76, 77]),
                    LineSeries("Allocated", [58, 59, 61, 63, 66, 70, 73, 74, 73, 72, 71, 70, 69, 70, 72, 73]),
                    LineSeries("Buffer", [12, 11, 10, 9, 8, 6, 4, 3, 3, 4, 5, 6, 7, 6, 5, 4]),
                ],
                threshold=68.0,
                annotations={7: "launch prep", 15: "quarter end"},
            ),
            "line-burndown-ideal": LineChartSpec(
                title="G. Burndown vs Ideal",
                x_labels=labels,
                series=[
                    LineSeries("Remaining", [98, 94, 90, 88, 85, 83, 80, 78, 74, 71, 67, 63, 58, 52, 45, 38]),
                    LineSeries("Ideal", [98, 92, 86, 80, 74, 68, 62, 56, 50, 44, 38, 32, 26, 20, 14, 8]),
                ],
                threshold=50.0,
                annotations={6: "scope add", 13: "scope cut"},
            ),
            "line-lead-vs-cycle": LineChartSpec(
                title="H. Lead vs Cycle Time",
                x_labels=labels,
                series=[
                    LineSeries("LeadDays", [9.2, 9.4, 9.6, 10.0, 10.5, 11.0, 10.8, 10.3, 9.8, 9.3, 8.9, 8.6, 8.4, 8.2, 8.1, 8.0]),
                    LineSeries("CycleDays", [4.1, 4.2, 4.4, 4.8, 5.1, 5.3, 5.2, 5.0, 4.8, 4.6, 4.4, 4.3, 4.2, 4.1, 4.1, 4.0]),
                ],
                threshold=8.5,
                annotations={5: "review queue", 11: "triage policy"},
            ),
        }

    def _clamp_line_window(self, cards: list[IdeationCard]) -> None:
        selected = None
        for card in cards:
            if card.idea_id == self.selected_idea_id:
                selected = card
                break
        if selected is None:
            self._line_window_start = 0
            return
        spec = self._line_spec(selected)
        if spec is None:
            self._line_window_start = 0
            return
        max_start = max(0, len(spec.x_labels) - self._line_window_size)
        self._line_window_start = max(0, min(max_start, self._line_window_start))
        self._line_selected_series = max(0, min(len(spec.series) - 1, self._line_selected_series))

    def _all_cards(self) -> list[IdeationCard]:
        return [
            IdeationCard("line-minimal", "Line A: Minimal Trend Signal", "delivery", "Single-focus line for fast status scanning.", "line", "Use one metric + target to minimize noise.", "line-minimal"),
            IdeationCard("line-analytical", "Line B: Analytical Overlay", "delivery", "Actual vs rolling average vs forecast in one frame.", "line", "Spot divergence early and call out interventions.", "line-analytical"),
            IdeationCard("line-story", "Line C: Storytelling Roadmap", "delivery", "Narrative line chart with meaningful event markers.", "line", "Use annotations to tie metric shifts to actions.", "line-story"),
            IdeationCard("line-failure-rate", "Line D: CI Failure Rate", "quality", "Tracks failure pressure against SLO threshold.", "line", "Alert when fail-rate stays above SLO for 2+ windows.", "line-failure-rate"),
            IdeationCard("line-review-latency", "Line E: PR Review Latency", "flow", "Shows median and p90 review wait to expose bottlenecks.", "line", "Use rota changes as event annotations.", "line-review-latency"),
            IdeationCard("line-capacity-pulse", "Line F: Capacity Pulse", "capacity", "Visualizes planned, allocated, and buffer dynamics.", "line", "Track buffer depletion before launch phases.", "line-capacity-pulse"),
            IdeationCard("line-burndown-ideal", "Line G: Burndown vs Ideal", "delivery", "Compares actual remaining work against ideal burn trajectory.", "line", "Highlight sustained slippage segments for planning correction.", "line-burndown-ideal"),
            IdeationCard("line-lead-vs-cycle", "Line H: Lead vs Cycle Time", "flow", "Dual latency trend to separate queueing delay from execution delay.", "line", "Use widening spread as a queue-health warning.", "line-lead-vs-cycle"),
            IdeationCard("flow-cycle-control", "Cycle Time Control Bands", "flow", "Percentile controls for early drift detection.", "control", "Flag p85 breaches and pin to incident trail."),
            IdeationCard("flow-aging-histogram", "Aging WIP Histogram", "flow", "Spots stale work clusters before they become blockers.", "aging", "Link 15d+ bucket directly to drilldown list."),
            IdeationCard("quality-blocker-heatmap", "Blocker Heatmap By Team", "quality", "Maps blocker concentration by team/day cadence.", "heatmap", "Overlay failing checks for stronger triage signal."),
            IdeationCard("quality-review-funnel", "PR Review Funnel", "quality", "Identifies conversion loss from draft to merge.", "funnel", "Track drop-offs after policy changes."),
            IdeationCard("quality-ci-radar", "CI Flake Radar", "quality", "Summarizes flaky signature distribution by cause.", "radar", "Use to prioritize reliability backlog."),
            IdeationCard("capacity-stacked", "Team Capacity Stack", "capacity", "Done/active/blocked composition per engineer.", "stacked", "Pair with what-if rebalance suggestions."),
            IdeationCard("capacity-dependency-matrix", "Dependency Pressure Matrix", "capacity", "Cross-team dependency load and directional pressure.", "matrix", "Jump from hot cells to issue clusters."),
            IdeationCard("portfolio-confidence", "Delivery Confidence Forecast", "portfolio", "Projects probability of landing on time.", "forecast", "Tie threshold breaches to exec digest alerts."),
            IdeationCard("portfolio-risk-impact", "Risk vs Impact Quadrant", "portfolio", "Balances strategic bets by risk-adjusted value.", "quadrant", "Prioritize top-right with mitigation owners."),
            IdeationCard("portfolio-activity-calendar", "Activity Calendar Heat Strip", "portfolio", "Shipping rhythm and anomaly detection by month.", "calendar", "Use streak breaks for incident retros."),
            IdeationCard("portfolio-release-velocity", "Release Velocity Ladder", "portfolio", "Week-over-week shipped value ladder by product stream.", "forecast", "Compare stream momentum and rebalance investment."),
            IdeationCard("quality-defect-parade", "Defect Arrival Parade", "quality", "Arrival vs closure cadence for production defects.", "control", "Surface when inflow exceeds closure capacity."),
        ]

    def _wrap(self, value: str, width: int, indent: str = "   ") -> str:
        return fill(value.strip(), width=width, subsequent_indent=indent)
