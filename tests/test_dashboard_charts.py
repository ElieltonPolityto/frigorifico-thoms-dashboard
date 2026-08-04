"""Regression tests for the dashboard chart layout."""

from __future__ import annotations

from pathlib import Path
import unittest

from dashboard_charts import (
    MAIN_METRIC_COLORS,
    continuous_phase_chart,
    hourly_metric_chart,
    main_cycle_chart,
    weight_loss_comparison_chart,
)
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

    def test_hourly_chart_combines_loading_and_cooling_to_target_with_matrix(self):
        selected_cycles = self.cycles[:3]
        selected_hours = []
        for cycle in selected_cycles:
            selected_hours.extend(cycle_frame(self.data, cycle, "Espeto")["hour_label"].unique())

        chart = hourly_metric_chart(selected_cycles, self.data, "Espeto", selected_hours)
        spec = chart.to_dict()

        self.assertEqual(len(spec["vconcat"]), 2)
        self.assertNotIn(PHASE_POST_TARGET, str(spec))
        self.assertEqual(spec["vconcat"][0]["mark"]["type"], "bar")
        hour_sort = spec["vconcat"][0]["encoding"]["x"]["sort"]
        self.assertIn("C0", hour_sort)
        self.assertIn("R0", hour_sort)
        self.assertLess(hour_sort.index("C0"), hour_sort.index("R0"))
        matrix_layers = spec["vconcat"][1]["layer"]
        self.assertEqual(
            [layer["mark"]["type"] for layer in matrix_layers],
            ["rect", "text"],
        )
        self.assertIn("Ciclo curto", str(spec["vconcat"][1]))

    def test_continuous_hourly_metrics_use_lines_and_points_without_bar_offsets(self):
        selected_cycles = self.cycles[:3]
        selected_hours = []
        for cycle in selected_cycles:
            selected_hours.extend(cycle_frame(self.data, cycle, "Espeto")["hour_label"].unique())

        for metric in ("Peso", "DT_ref", "Umidade", "Glicol", "Retorno de ar"):
            chart = hourly_metric_chart(selected_cycles, self.data, metric, selected_hours)
            spec = chart.to_dict()

            plot = spec["vconcat"][0]
            self.assertEqual(
                [layer["mark"]["type"] for layer in plot["layer"]],
                ["line", "point"],
            )
            self.assertNotIn("xOffset", str(plot))

    def test_ventilation_uses_step_lines_and_cycle_markers(self):
        selected_cycles = self.cycles[:3]
        selected_hours = []
        for cycle in selected_cycles:
            selected_hours.extend(cycle_frame(self.data, cycle, "Espeto")["hour_label"].unique())

        chart = hourly_metric_chart(selected_cycles, self.data, "Ventilacao", selected_hours)
        spec = chart.to_dict()

        plot = spec["vconcat"][0]
        self.assertEqual(plot["layer"][0]["mark"]["interpolate"], "step-after")
        self.assertEqual(plot["layer"][1]["encoding"]["shape"]["field"], "Ciclo")
        self.assertEqual(plot["layer"][0]["encoding"]["strokeDash"]["field"], "Ciclo")

    def test_continuous_chart_combines_loading_and_cooling_and_hides_post_target(self):
        selected_cycles = self.cycles[:3]
        selected_hours = []
        for cycle in selected_cycles:
            selected_hours.extend(cycle_frame(self.data, cycle, "Espeto")["hour_label"].unique())

        chart = continuous_phase_chart(selected_cycles, self.data, "Espeto", selected_hours)
        spec = chart.to_dict()

        self.assertIn("layer", spec)
        line = spec["layer"][0]
        self.assertEqual(line["mark"]["type"], "line")
        self.assertEqual(
            line["encoding"]["x"]["field"],
            "hours_from_cycle_start",
        )
        self.assertNotIn(PHASE_POST_TARGET, str(spec))

    def test_main_chart_uses_four_aligned_bands_and_expected_domains(self):
        selected_cycles = self.cycles[:3]
        selected_hours = []
        for cycle in selected_cycles:
            selected_hours.extend(cycle_frame(self.data, cycle, "Espeto")["hour_label"].unique())

        chart = main_cycle_chart(
            selected_cycles[0],
            selected_cycles,
            self.data,
            ["Retorno de ar", "Espeto", "Ventilacao", "Umidade", "Peso"],
            selected_hours,
            interactive=False,
        )
        spec = chart.to_dict()

        self.assertEqual(len(spec["vconcat"]), 4)
        temperature_y = spec["vconcat"][0]["layer"][2]["encoding"]["y"]
        temperature_x = spec["vconcat"][0]["layer"][2]["encoding"]["x"]
        ventilation_y = spec["vconcat"][1]["layer"][2]["encoding"]["y"]
        humidity_y = spec["vconcat"][2]["layer"][2]["encoding"]["y"]
        self.assertEqual(temperature_y["scale"]["domain"], [-10, 50])
        self.assertEqual(temperature_x["scale"], {"domain": [0, 25.75], "nice": False})
        self.assertEqual(temperature_x["axis"]["values"], list(range(26)))
        self.assertEqual(ventilation_y["scale"]["domain"], [0, 100])
        self.assertEqual(humidity_y["scale"]["domain"], [92, 100])
        self.assertEqual(humidity_y["title"], "Umidade relativa (%)")

        ventilation_lines = [
            layer
            for layer in spec["vconcat"][1]["layer"]
            if layer.get("mark", {}).get("type") == "line"
        ]
        self.assertEqual(len(ventilation_lines), 2)
        self.assertEqual(ventilation_lines[0]["encoding"]["y"]["title"], "Ventilacao (%)")
        self.assertEqual(ventilation_lines[0]["encoding"]["y"]["scale"]["domain"], [0, 100])
        self.assertIsNone(ventilation_lines[1]["encoding"]["y"]["title"])
        self.assertEqual(ventilation_lines[1]["encoding"]["y"]["axis"]["orient"], "right")
        self.assertEqual(ventilation_lines[1]["encoding"]["y"]["axis"]["labelAlign"], "right")
        self.assertEqual(
            ventilation_lines[1]["encoding"]["y"]["axis"]["labelExpr"],
            "datum.label + ' °C'",
        )
        self.assertEqual(
            ventilation_lines[1]["encoding"]["color"]["scale"]["domain"],
            ["Ventilacao", "DT Atual"],
        )
        self.assertEqual(spec["vconcat"][1]["resolve"]["scale"]["y"], "independent")
        self.assertEqual(spec["padding"], {"right": 65})

        temperature_colors = [
            layer["encoding"]["color"]
            for layer in spec["vconcat"][0]["layer"]
            if layer.get("mark", {}).get("type") == "line"
        ]
        self.assertEqual(len(temperature_colors), 1)
        for color in temperature_colors:
            self.assertEqual(color["field"], "metric_label")
            self.assertEqual(color["legend"], {"orient": "top", "title": None})
            self.assertEqual(color["scale"]["domain"], ["Retorno do ar", "Espeto"])
            self.assertEqual(
                color["scale"]["range"],
                [MAIN_METRIC_COLORS["Retorno de ar"], MAIN_METRIC_COLORS["Espeto"]],
            )

        weight_layers = spec["vconcat"][3]["layer"]
        self.assertEqual(weight_layers[2]["mark"]["type"], "line")
        self.assertEqual(weight_layers[2]["mark"]["opacity"], 0.32)
        self.assertEqual(weight_layers[2]["encoding"]["y"]["field"], "weight_kg")
        self.assertEqual(weight_layers[2]["encoding"]["y"]["title"], "Peso (kg)")
        self.assertEqual(weight_layers[3]["mark"]["type"], "line")
        self.assertEqual(weight_layers[3]["encoding"]["y"]["field"], "weight_trend_kg")
        self.assertIsNone(weight_layers[3]["encoding"]["y"]["axis"])
        encoded_y_fields = {
            layer["encoding"]["y"].get("field")
            for layer in weight_layers
            if "encoding" in layer and "y" in layer["encoding"]
        }
        self.assertNotIn("loss_display_kg", encoded_y_fields)
        self.assertEqual(
            [layer["mark"]["type"] for layer in weight_layers].count("point"),
            2,
        )
        self.assertEqual(
            spec["vconcat"][3]["title"]["text"],
            "Peso medido até 7 °C (kg) · escala ampliada · sem peso válido no instante de 7 °C",
        )

    def test_weight_loss_chart_combines_percentage_and_kg_in_one_panel(self):
        selected_cycles = self.cycles[:3]
        selected_hours = []
        for cycle in selected_cycles:
            selected_hours.extend(cycle_frame(self.data, cycle, "Espeto")["hour_label"].unique())

        spec = weight_loss_comparison_chart(
            selected_cycles,
            self.data,
            selected_hours,
        ).to_dict()

        self.assertNotIn("vconcat", spec)
        self.assertEqual([layer["mark"]["type"] for layer in spec["layer"]], ["rule", "line", "line"])
        self.assertEqual(spec["layer"][1]["encoding"]["y"]["title"], "Perda acumulada (%)")
        self.assertEqual(spec["layer"][2]["encoding"]["y"]["title"], "Perda acumulada (kg)")
        self.assertEqual(spec["layer"][2]["encoding"]["y"]["axis"]["orient"], "right")


if __name__ == "__main__":
    unittest.main()
