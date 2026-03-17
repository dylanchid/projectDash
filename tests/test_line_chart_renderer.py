from projectdash.charts import LineChartRenderer, LineChartSpec, LineSeries


def test_line_chart_renderer_compact_and_detailed() -> None:
    renderer = LineChartRenderer()
    spec = LineChartSpec(
        title="Cycle Time",
        x_labels=["W1", "W2", "W3", "W4", "W5", "W6"],
        series=[
            LineSeries("Actual", [3.0, 3.2, 3.5, 3.1, 3.8, 3.4]),
            LineSeries("Target", [3.0, 3.0, 3.0, 3.0, 3.0, 3.0]),
        ],
        threshold=3.0,
        annotations={2: "scope jump", 5: "retro"},
    )

    compact = renderer.render_compact(spec, selected_series_index=0, window_start=0, window_size=6)
    detailed = renderer.render_detailed(spec, selected_series_index=0, window_start=0, window_size=6, height=6)

    assert "Actual" in compact
    assert "Cycle Time" in detailed
    assert "Events:" in detailed
    assert "Window 1-6" in detailed

    hires = renderer.render_hires(spec, selected_series_index=0, window_start=0, window_size=6, cell_rows=2)
    assert "[hires]" in hires
    assert any(ord(ch) >= 0x2800 and ord(ch) <= 0x28FF for ch in hires)
