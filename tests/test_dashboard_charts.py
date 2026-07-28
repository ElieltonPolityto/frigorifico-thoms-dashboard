"""Regression tests for the dashboard chart layout."""

from __future__ import annotations

from pathlib import Path
import unittest

from dashboard_charts import continuous_phase_chart, hourly_metric_chart
from thoms_dashboard_data import (
    PHASE_LOADING,
    PHASE_POST_TARGET,
    PHASE_TO_TARGET,
    cycle_frame,
    detect_valid_cycles,
    load_supervision_data,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class HourlyMetricChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_supervision_data(PROJECT_ROOT / "dados_entrada")
        cls.cycles = detect_valid_cycles(cls.data)

    def test_bars_show_loading_and_cooling_to_target_only(self):
        selected_cycles = self.cycles[:3]
        selected_hours = []
        for cycle in selected_cycles:
            selected_hours.extend(cycle_frame(self.data, cycle, "Espeto")["hour_label"].unique())

        chart = hourly_metric_chart(selected_cycles, self.data, "Espeto", selected_hours)
        spec = chart.to_dict()

        self.assertEqual(len(spec["vconcat"]), 2)
        self.assertEqual(
            [panel["title"] for panel in spec["vconcat"]],
            [PHASE_LOADING, PHASE_TO_TARGET],
        )
        self.assertNotIn(PHASE_POST_TARGET, str(spec))
        self.assertTrue(
            all(panel["mark"]["type"] == "bar" for panel in spec["vconcat"])
        )

    def test_weight_loss_uses_lines_and_points_without_bar_offsets(self):
        selected_cycles = self.cycles[:3]
        selected_hours = []
        for cycle in selected_cycles:
            selected_hours.extend(cycle_frame(self.data, cycle, "Espeto")["hour_label"].unique())

        chart = hourly_metric_chart(selected_cycles, self.data, "Peso", selected_hours)
        spec = chart.to_dict()

        for panel in spec["vconcat"]:
            self.assertEqual(
                [layer["mark"]["type"] for layer in panel["layer"]],
                ["line", "point"],
            )
            self.assertNotIn("xOffset", str(panel))

    def test_continuous_chart_hides_post_target_panel(self):
        selected_cycles = self.cycles[:3]
        selected_hours = []
        for cycle in selected_cycles:
            selected_hours.extend(cycle_frame(self.data, cycle, "Espeto")["hour_label"].unique())

        chart = continuous_phase_chart(selected_cycles, self.data, "Espeto", selected_hours)
        spec = chart.to_dict()

        self.assertEqual(len(spec["vconcat"]), 2)
        self.assertEqual(
            [panel["title"] for panel in spec["vconcat"]],
            [PHASE_LOADING, PHASE_TO_TARGET],
        )
        self.assertNotIn(PHASE_POST_TARGET, str(spec))


if __name__ == "__main__":
    unittest.main()
