from pathlib import Path
import unittest

import pandas as pd

from thoms_dashboard_data import (
    PHASE_LOADING,
    PHASE_POST_TARGET,
    PHASE_TO_TARGET,
    cycle_frame,
    cycle_metrics,
    cycle_weight_quality,
    detect_valid_cycles,
    hourly_phase_summary,
    load_supervision_data,
    rank_cycles,
    valid_weight_series,
    weight_loss_frame,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DashboardDataIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_supervision_data(PROJECT_ROOT / "dados_entrada")
        cls.cycles = detect_valid_cycles(cls.data)

    def test_cycle_frame_uses_three_phase_relative_labels(self):
        cycle = self.cycles[0]
        frame = cycle_frame(self.data, cycle, "Espeto")

        self.assertEqual(
            set(frame["phase"].unique()),
            {PHASE_LOADING, PHASE_TO_TARGET, PHASE_POST_TARGET},
        )
        self.assertTrue(frame.loc[frame["phase"].eq(PHASE_LOADING), "hour_label"].str.startswith("C").all())
        self.assertTrue(frame.loc[frame["phase"].eq(PHASE_TO_TARGET), "hour_label"].str.startswith("R").all())
        self.assertTrue(frame.loc[frame["phase"].eq(PHASE_POST_TARGET), "hour_label"].str.startswith("P").all())
        for phase in frame["phase"].unique():
            first = frame.loc[frame["phase"].eq(phase), "hours_from_phase_start"].iloc[0]
            self.assertAlmostEqual(float(first), 0.0, places=6)

    def test_cycle_frame_reads_current_dt_directly_from_source(self):
        cycle = self.cycles[0]
        frame = cycle_frame(self.data, cycle, "DT_atual")
        source = self.data.loc[cycle.start_index : cycle.end_index, "DT Atual"].reset_index(drop=True)

        self.assertEqual(frame["unit"].iloc[0], "°C")
        pd.testing.assert_series_equal(frame["value"].reset_index(drop=True), source, check_names=False)

    def test_phase_durations_reconcile_to_total_cycle(self):
        for cycle in self.cycles:
            metrics = cycle_metrics(self.data, cycle)
            post = metrics["Duracao pos meta"] or 0
            self.assertAlmostEqual(
                metrics["Duracao carga"]
                + metrics["Duracao ate meta"]
                + post,
                metrics["Duracao carga"] + metrics["Duracao resfriamento"],
                places=6,
            )

    def test_hourly_summary_exposes_bounded_coverage(self):
        summary = hourly_phase_summary(self.data, self.cycles[0], "Espeto")
        self.assertFalse(summary.empty)
        self.assertTrue(summary["coverage_minutes"].between(0, 60).all())
        self.assertTrue((summary["partial"] == (summary["coverage_minutes"] < 45)).all())

    def test_ranking_excludes_cycles_without_a_valid_weight_loss(self):
        ranking = rank_cycles(self.data, self.cycles)
        ranked_labels = set(ranking["label"])
        ineligible_labels = {
            cycle.label
            for cycle in self.cycles
            if not isinstance(cycle_metrics(self.data, cycle)["Perda"], (int, float))
            or cycle_metrics(self.data, cycle)["Perda"] < 0
            or bool(cycle_metrics(self.data, cycle)["Peso suspeito"])
        }
        self.assertTrue(ineligible_labels)
        self.assertTrue(ranked_labels.isdisjoint(ineligible_labels))
        self.assertTrue((ranking["score"].diff().dropna() >= 0).all())

    def test_weight_loss_uses_the_sample_five_minutes_after_loading_peak(self):
        cycle = next(cycle for cycle in self.cycles if cycle.label.startswith("19/06/2026"))
        metrics = cycle_metrics(self.data, cycle)

        self.assertEqual(str(metrics["Hora referencia peso"]), "2026-06-19 11:37:00")
        self.assertAlmostEqual(float(metrics["Peso referencia"]), 98.8, places=6)
        self.assertEqual(metrics["Peso inicial"], metrics["Peso referencia"])
        self.assertAlmostEqual(float(metrics["Peso final"]), 96.8, places=6)
        self.assertAlmostEqual(float(metrics["Perda"]), 2.0242914979757085, places=12)

        ranking = rank_cycles(self.data, self.cycles)
        ranked_loss = ranking.loc[ranking["label"].eq(cycle.label), "weight_loss"].iloc[0]
        self.assertAlmostEqual(float(ranked_loss), float(metrics["Perda"]), places=12)

    def test_weight_limits_preserve_raw_values_and_exclude_out_of_range_series(self):
        raw = self.data.copy()
        raw_weight = raw["Peso atual"].copy()
        valid = valid_weight_series(raw)

        self.assertTrue(raw_weight.equals(raw["Peso atual"]))
        self.assertTrue(valid.dropna().gt(50).all())
        self.assertTrue(valid.dropna().le(300).all())
        self.assertTrue(valid.loc[raw_weight.gt(300)].isna().all())

    def test_weight_loss_frame_reconciles_absolute_and_percentage_loss(self):
        cycle = next(cycle for cycle in self.cycles if cycle.label.startswith("19/06/2026"))
        frame = weight_loss_frame(self.data, cycle)
        valid = frame.dropna(subset=["weight_kg"])

        self.assertFalse(valid.empty)
        self.assertTrue(frame["is_reference"].any())
        self.assertTrue(frame["is_target"].any())
        reference = valid.loc[valid["is_reference"], "weight_kg"].iloc[0]
        self.assertTrue(
            (
                valid["loss_pct"]
                .sub(valid["loss_kg"] / reference * 100)
                .abs()
                .lt(1e-9)
                .all()
            )
        )

    def test_weight_quality_flags_abrupt_cycles_and_excludes_them_from_ranking(self):
        suspicious = [
            cycle for cycle in self.cycles if cycle_weight_quality(self.data, cycle).suspect
        ]
        ranking = rank_cycles(self.data, self.cycles)

        self.assertEqual(len(self.cycles), 42)
        self.assertEqual(len(suspicious), 8)
        self.assertEqual(len(ranking), 27)
        self.assertTrue(ranking["label"].isin([cycle.label for cycle in suspicious]).sum() == 0)


if __name__ == "__main__":
    unittest.main()
