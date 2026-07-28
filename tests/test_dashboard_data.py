from pathlib import Path
import unittest

from thoms_dashboard_data import (
    PHASE_LOADING,
    PHASE_POST_TARGET,
    PHASE_TO_TARGET,
    cycle_frame,
    cycle_metrics,
    detect_valid_cycles,
    hourly_phase_summary,
    load_supervision_data,
    rank_cycles,
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

    def test_ranking_excludes_negative_weight_loss(self):
        ranking = rank_cycles(self.data, self.cycles)
        ranked_labels = set(ranking["label"])
        negative_labels = {
            cycle.label
            for cycle in self.cycles
            if isinstance(cycle_metrics(self.data, cycle)["Perda"], (int, float))
            and cycle_metrics(self.data, cycle)["Perda"] < 0
        }
        self.assertTrue(negative_labels)
        self.assertTrue(ranked_labels.isdisjoint(negative_labels))
        self.assertTrue((ranking["score"].diff().dropna() >= 0).all())


if __name__ == "__main__":
    unittest.main()
