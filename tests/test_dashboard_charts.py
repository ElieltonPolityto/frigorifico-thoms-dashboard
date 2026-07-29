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
            [panel["vconcat"][0]["title"] for panel in spec["vconcat"]],
            [PHASE_LOADING, PHASE_TO_TARGET],
        )
        self.assertNotIn(PHASE_POST_TARGET, str(spec))
        self.assertTrue(
            all(
                panel["vconcat"][0]["mark"]["type"] == "bar"
                for panel in spec["vconcat"]
            )
        )
        for panel in spec["vconcat"]:
            matrix_layers = panel["vconcat"][1]["layer"]
            self.assertEqual(
                [layer["mark"]["type"] for layer in matrix_layers],
                ["rect", "text"],
            )
            self.assertIn("Ciclo curto", str(panel["vconcat"][1]))

    def test_continuous_hourly_metrics_use_lines_and_points_without_bar_offsets(self):
        selected_cycles = self.cycles[:3]
        selected_hours = []
        for cycle in selected_cycles:
            selected_hours.extend(cycle_frame(self.data, cycle, "Espeto")["hour_label"].unique())

        for metric in ("Peso", "DT_ref", "Umidade", "Glicol", "Retorno de ar"):
            chart = hourly_metric_chart(selected_cycles, self.data, metric, selected_hours)
            spec = chart.to_dict()

            for panel in spec["vconcat"]:
                plot = panel["vconcat"][0]
                self.assertEqual(
                    [layer["mark"]["type"] for layer in plot["layer"]],
                    ["line", "point"],
                )
                self.assertNotIn("xOffset", str(plot))

    def test_ventilation_uses_step_lines_with_square_markers(self):
        selected_cycles = self.cycles[:3]
        selected_hours = []
        for cycle in selected_cycles:
            selected_hours.extend(cycle_frame(self.data, cycle, "Espeto")["hour_label"].unique())

        chart = hourly_metric_chart(selected_cycles, self.data, "Ventilacao", selected_hours)
        spec = chart.to_dict()

        for panel in spec["vconcat"]:
            plot = panel["vconcat"][0]
            self.assertEqual(plot["layer"][0]["mark"]["interpolate"], "step-after")
            self.assertEqual(plot["layer"][1]["mark"]["shape"], "square")

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
