from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineSeries:
    name: str
    values: list[float]
    glyph: str = "●"


@dataclass(frozen=True)
class LineChartSpec:
    title: str
    x_labels: list[str]
    series: list[LineSeries]
    threshold: float | None = None
    annotations: dict[int, str] | None = None


class LineChartRenderer:
    _LEVEL_GLYPHS = " ▁▂▃▄▅▆▇█"

    def render_compact(
        self,
        spec: LineChartSpec,
        *,
        selected_series_index: int = 0,
        window_start: int = 0,
        window_size: int = 8,
    ) -> str:
        if not spec.series or not spec.x_labels:
            return "   no line data"
        selected = spec.series[selected_series_index % len(spec.series)]
        clipped, _min_value, _max_value = self._window_values(selected.values, window_start, window_size)
        if not clipped:
            return "   no line data"
        spark = self._sparkline(clipped)
        latest = clipped[-1]
        earliest = clipped[0]
        delta = latest - earliest
        sign = "+" if delta >= 0 else ""
        labels = self._window_labels(spec.x_labels, window_start, len(clipped))
        left = labels[0] if labels else "-"
        right = labels[-1] if labels else "-"
        return (
            f"   {selected.name[:10].ljust(10)} {spark}  {latest:.1f} ({sign}{delta:.1f})\n"
            f"   {left} -> {right}"
        )

    def render_detailed(
        self,
        spec: LineChartSpec,
        *,
        selected_series_index: int = 0,
        window_start: int = 0,
        window_size: int = 10,
        height: int = 7,
    ) -> str:
        if not spec.series or not spec.x_labels:
            return "No line data."
        selected_series_index = selected_series_index % len(spec.series)

        windowed = []
        min_value = None
        max_value = None
        for series in spec.series:
            values, local_min, local_max = self._window_values(series.values, window_start, window_size)
            windowed.append(values)
            if values:
                min_value = local_min if min_value is None else min(min_value, local_min)
                max_value = local_max if max_value is None else max(max_value, local_max)
        if min_value is None or max_value is None:
            return "No line data."

        if min_value == max_value:
            max_value += 1.0

        labels = self._window_labels(spec.x_labels, window_start, len(windowed[0]))
        points = max(len(labels), 1)
        plot_width = max(1, (points * 2) - 1)
        canvas = [[" " for _ in range(plot_width)] for _ in range(height)]

        if spec.threshold is not None:
            threshold_row = self._quantize(spec.threshold, min_value, max_value, height)
            for y in range(0, threshold_row):
                for x in range(0, plot_width, 2):
                    if canvas[y][x] == " ":
                        canvas[y][x] = "·"
            for x in range(plot_width):
                canvas[threshold_row][x] = "·"

        for series_index, values in enumerate(windowed):
            glyph = "●" if series_index == selected_series_index else "•"
            for point_index, value in enumerate(values):
                x = point_index * 2
                y = self._quantize(value, min_value, max_value, height)
                canvas[y][x] = glyph
                if point_index == 0:
                    continue
                previous_value = values[point_index - 1]
                previous_x = x - 2
                previous_y = self._quantize(previous_value, min_value, max_value, height)
                connector_x = x - 1
                if previous_y == y:
                    connector = "─"
                elif previous_y > y:
                    connector = "╱"
                else:
                    connector = "╲"
                if 0 <= connector_x < plot_width:
                    existing = canvas[previous_y][connector_x] if 0 <= previous_y < height else " "
                    if existing in {" ", "·"}:
                        canvas[previous_y][connector_x] = connector

        rows: list[str] = []
        for row_index in range(height):
            y_value = max_value - ((max_value - min_value) * (row_index / max(1, height - 1)))
            row_chars = "".join(canvas[row_index])
            rows.append(f"{y_value:>5.1f} |{row_chars}")

        axis = "      +" + "-" * plot_width
        label_chars = [" " for _ in range(plot_width)]
        tick_step = max(1, int(round(points / 6)))
        tick_positions = list(range(0, points, tick_step))
        if tick_positions and tick_positions[-1] != points - 1:
            tick_positions.append(points - 1)
        for index in tick_positions:
            x = index * 2
            if 0 <= x < plot_width:
                label_chars[x] = labels[index][-1] if labels[index] else "·"
        label_row = "       " + "".join(label_chars)

        selected = spec.series[selected_series_index]
        selected_values = windowed[selected_series_index]
        latest = selected_values[-1] if selected_values else 0.0
        avg = (sum(selected_values) / len(selected_values)) if selected_values else 0.0
        legend = []
        for index, series in enumerate(spec.series):
            marker = "*" if index == selected_series_index else " "
            series_values = windowed[index]
            last = series_values[-1] if series_values else 0.0
            legend.append(f"{marker}{series.name}:{last:.1f}")
        threshold_label = f"  thr:{spec.threshold:.1f}" if spec.threshold is not None else ""
        annotation_line = self._annotation_text(spec, window_start, points)
        axis_label = f"x {labels[0]}..{labels[-1]}  y {min_value:.1f}-{max_value:.1f}"
        return (
            f"{spec.title}\n"
            f"{'  '.join(legend)}  avg:{avg:.1f}{threshold_label}\n"
            + "\n".join(rows)
            + "\n"
            + axis
            + "\n"
            + label_row
            + ("\n" + annotation_line if annotation_line else "")
            + f"\n{axis_label}"
            + f"\nWindow {window_start + 1}-{window_start + points}  focus:{selected.name}  latest:{latest:.1f}"
        )

    def render_hires(
        self,
        spec: LineChartSpec,
        *,
        selected_series_index: int = 0,
        window_start: int = 0,
        window_size: int = 10,
        cell_rows: int = 3,
    ) -> str:
        if not spec.series or not spec.x_labels:
            return "No line data."
        selected_series_index = selected_series_index % len(spec.series)

        windowed = []
        min_value = None
        max_value = None
        for series in spec.series:
            values, local_min, local_max = self._window_values(series.values, window_start, window_size)
            windowed.append(values)
            if values:
                min_value = local_min if min_value is None else min(min_value, local_min)
                max_value = local_max if max_value is None else max(max_value, local_max)
        if min_value is None or max_value is None:
            return "No line data."
        if min_value == max_value:
            max_value += 1.0

        labels = self._window_labels(spec.x_labels, window_start, len(windowed[0]))
        points = max(len(labels), 1)
        pixel_height = max(4, cell_rows * 4)
        pixel_width = max(4, points * 2)
        grid = [[False for _ in range(pixel_width)] for _ in range(pixel_height)]

        def _set_pixel(x: int, y: int) -> None:
            if 0 <= x < pixel_width and 0 <= y < pixel_height:
                grid[y][x] = True

        def _value_to_y(value: float) -> int:
            normalized = (value - min_value) / (max_value - min_value)
            return int(round((1.0 - normalized) * (pixel_height - 1)))

        def _index_to_x(index: int) -> int:
            if points <= 1:
                return 0
            return int(round((index / (points - 1)) * (pixel_width - 1)))

        if spec.threshold is not None:
            threshold_y = _value_to_y(spec.threshold)
            for y in range(0, threshold_y):
                for x in range(0, pixel_width, 4):
                    _set_pixel(x, y)
            for x in range(0, pixel_width, 2):
                _set_pixel(x, threshold_y)

        for series_index, values in enumerate(windowed):
            previous_x = None
            previous_y = None
            for point_index, value in enumerate(values):
                x = _index_to_x(point_index)
                y = _value_to_y(value)
                _set_pixel(x, y)
                if series_index == selected_series_index and y + 1 < pixel_height:
                    _set_pixel(x, y + 1)
                if previous_x is not None and previous_y is not None:
                    self._draw_line(previous_x, previous_y, x, y, _set_pixel)
                previous_x, previous_y = x, y

        braille_rows = self._pixels_to_braille(grid, cell_rows=cell_rows)
        selected = spec.series[selected_series_index]
        selected_values = windowed[selected_series_index]
        latest = selected_values[-1] if selected_values else 0.0
        legend = []
        for index, series in enumerate(spec.series):
            marker = "*" if index == selected_series_index else " "
            values = windowed[index]
            legend.append(f"{marker}{series.name}:{(values[-1] if values else 0.0):.1f}")
        threshold_label = f"  thr:{spec.threshold:.1f}" if spec.threshold is not None else ""
        annotation_line = self._annotation_text(spec, window_start, points)
        x_labels = f"{labels[0] if labels else '-'} -> {labels[-1] if labels else '-'}"
        axis_label = f"x {labels[0] if labels else '-'}..{labels[-1] if labels else '-'}  y {min_value:.1f}-{max_value:.1f}"
        return (
            f"{spec.title} [hires]\n"
            f"{'  '.join(legend)}{threshold_label}\n"
            f"max {max_value:.1f} |{braille_rows[0]}\n"
            + "\n".join(f"          |{row}" for row in braille_rows[1:-1])
            + (f"\nmin {min_value:.1f} |{braille_rows[-1]}" if len(braille_rows) > 1 else "")
            + f"\n          +{'-' * len(braille_rows[0])}\n"
            + f"          {x_labels}\n"
            + (annotation_line + "\n" if annotation_line else "")
            + f"{axis_label}\n"
            + f"Window {window_start + 1}-{window_start + points}  focus:{selected.name}  latest:{latest:.1f}"
        )

    def _annotation_text(self, spec: LineChartSpec, window_start: int, points: int) -> str:
        if not spec.annotations:
            return ""
        visible = []
        window_end = window_start + points - 1
        for index, label in sorted(spec.annotations.items()):
            if window_start <= index <= window_end:
                visible.append(f"{index + 1}:{label}")
        return "Events: " + " | ".join(visible) if visible else ""

    def _draw_line(self, x0: int, y0: int, x1: int, y1: int, set_pixel) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        while True:
            set_pixel(x, y)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    def _pixels_to_braille(self, grid: list[list[bool]], *, cell_rows: int) -> list[str]:
        pixel_height = len(grid)
        pixel_width = len(grid[0]) if grid else 0
        cell_cols = (pixel_width + 1) // 2
        rows: list[str] = []
        for cell_row in range(cell_rows):
            chars: list[str] = []
            base_y = cell_row * 4
            for cell_col in range(cell_cols):
                base_x = cell_col * 2
                bits = 0
                bits |= 1 if self._pixel(grid, base_x, base_y) else 0  # dot 1
                bits |= 2 if self._pixel(grid, base_x, base_y + 1) else 0  # dot 2
                bits |= 4 if self._pixel(grid, base_x, base_y + 2) else 0  # dot 3
                bits |= 64 if self._pixel(grid, base_x, base_y + 3) else 0  # dot 7
                bits |= 8 if self._pixel(grid, base_x + 1, base_y) else 0  # dot 4
                bits |= 16 if self._pixel(grid, base_x + 1, base_y + 1) else 0  # dot 5
                bits |= 32 if self._pixel(grid, base_x + 1, base_y + 2) else 0  # dot 6
                bits |= 128 if self._pixel(grid, base_x + 1, base_y + 3) else 0  # dot 8
                chars.append(chr(0x2800 + bits))
            rows.append("".join(chars))
        return rows

    def _pixel(self, grid: list[list[bool]], x: int, y: int) -> bool:
        if y < 0 or x < 0:
            return False
        if y >= len(grid) or x >= len(grid[0]):
            return False
        return grid[y][x]

    def _window_values(self, values: list[float], start: int, window_size: int) -> tuple[list[float], float, float]:
        if not values:
            return [], 0.0, 0.0
        clamped_start = max(0, min(start, max(0, len(values) - 1)))
        window = values[clamped_start : clamped_start + max(1, window_size)]
        if not window:
            window = [values[-1]]
        return window, min(window), max(window)

    def _window_labels(self, labels: list[str], start: int, size: int) -> list[str]:
        clamped_start = max(0, min(start, max(0, len(labels) - 1)))
        return labels[clamped_start : clamped_start + max(1, size)]

    def _quantize(self, value: float, min_value: float, max_value: float, height: int) -> int:
        if max_value <= min_value:
            return 0
        normalized = (value - min_value) / (max_value - min_value)
        level = int((1.0 - normalized) * max(1, height - 1))
        return max(0, min(height - 1, level))

    def _sparkline(self, values: list[float]) -> str:
        if not values:
            return "-"
        if len(values) == 1:
            return "▁"
        low = min(values)
        high = max(values)
        spread = max(1e-9, high - low)
        chars = []
        for value in values:
            index = int(((value - low) / spread) * (len(self._LEVEL_GLYPHS) - 1))
            chars.append(self._LEVEL_GLYPHS[index])
        return "".join(chars)
