from types import SimpleNamespace
from unittest.mock import patch
import unittest

import pandas as pd

from app import cycle_summary_frame


class CycleSummaryCompatibilityTests(unittest.TestCase):
    def test_summary_accepts_legacy_initial_weight_key_during_hot_reload(self):
        legacy_metrics = {
            "Duracao carga": 1.0,
            "Duracao ate meta": 12.0,
            "Duracao pos meta": 2.0,
            "Peso inicial": 98.8,
            "Peso final": 96.8,
            "Perda": 2.02,
            "Espeto inicial": 40.0,
            "Tempo ate 7 C": 12.0,
            "DT_ref medio": 4.5,
        }
        cycle = SimpleNamespace(label="19/06/2026")

        with patch("app.cycle_metrics", return_value=legacy_metrics):
            summary = cycle_summary_frame([cycle], pd.DataFrame())

        self.assertEqual(summary.loc[0, "Peso de referencia"], "98.8 kg")


if __name__ == "__main__":
    unittest.main()
