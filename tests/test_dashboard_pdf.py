from pathlib import Path
import unittest

from dashboard_pdf import build_dashboard_pdf
from thoms_dashboard_data import cycle_frame, detect_valid_cycles, load_supervision_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DashboardPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_supervision_data(PROJECT_ROOT / "dados_entrada")
        cls.cycles = detect_valid_cycles(cls.data)[:2]
        cls.hours = list(
            dict.fromkeys(
                hour
                for cycle in cls.cycles
                for hour in cycle_frame(cls.data, cycle, "Espeto")["hour_label"].unique()
            )
        )

    def test_pdf_includes_the_new_main_and_weight_loss_charts(self):
        pdf = build_dashboard_pdf(
            selected_cycles=self.cycles,
            data=self.data,
            active_cycle=self.cycles[0],
            main_metrics=["Retorno de ar", "Espeto", "Ventilacao", "Umidade", "Peso"],
            bar_metrics=["Espeto"],
            selected_hours=self.hours,
            logo_path=PROJECT_ROOT / "static" / "brand" / "plotter-racks-logo-blue.png",
        )

        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 100_000)


if __name__ == "__main__":
    unittest.main()
