import calendar
import importlib.util
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "mod_forcing" / "climate" / "_3_refet_cimis_adj"
    / "step10b_apply_f1_adjustment_1921_2018.py"
)
spec = importlib.util.spec_from_file_location("refet_step10b", SCRIPT)
step10b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(step10b)


class Step10bTest(unittest.TestCase):
    def make_eto(self):
        data = {"Lon": [-120.0, -121.0], "Lat": [38.0, 39.0]}
        for year in range(1920, 2019):
            daily = 1.0 if year < 2004 else 2.0
            for month, name in enumerate(step10b.MONTH_NAMES, 1):
                inches = daily * calendar.monthrange(year, month)[1] / 25.4
                data[f"{name}-{year}"] = [inches, inches * 2]
        return pd.DataFrame(data)

    def test_overlap_f1_full_period_application_and_map_diagnostic(self):
        eto = self.make_eto()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "eto.csv"
            cimis_dir = root / "cimis"
            output_dir = root / "output"
            cimis_dir.mkdir()
            eto.to_csv(input_path, index=False)
            cimis = pd.DataFrame({
                "Lon": [-120.0, -121.0],
                "Lat": [38.0, 39.0],
                **{month: [6.0, np.nan] for month in step10b.MONTH_NAMES},
            })
            for year in range(2004, 2019):
                cimis.to_csv(
                    cimis_dir / f"CIMIS_MonthlyAvg_ETo_mmperday_ProductA_grid_{year}.csv",
                    index=False,
                )
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)
                with patch.object(step10b, "STEP10A_CSV", input_path), \
                     patch.object(step10b, "STEP6_CIMIS_DIR", cimis_dir), \
                     patch.object(step10b, "OUTPUT_DIR", output_dir):
                    step10b.main()

            prefix = "Product_A_"
            f1 = pd.read_csv(output_dir / f"{prefix}F1_table.csv")
            corrected = pd.read_csv(
                output_dir / f"{prefix}ETo_F1corrected_monthly_inpermonth.csv"
            )
            full = pd.read_csv(output_dir / f"{prefix}HS_monthly_avg_mmperday.csv")
            overlap = pd.read_csv(
                output_dir / f"{prefix}HS_monthly_avg_mmperday_2004_2018.csv"
            )

        self.assertEqual(list(corrected.columns), list(eto.columns))
        np.testing.assert_allclose(f1.loc[0, step10b.MONTH_NAMES].to_numpy(dtype=float), 3)
        np.testing.assert_allclose(f1.loc[1, step10b.MONTH_NAMES].to_numpy(dtype=float), 1)
        for col in ("Jan-1920", "Feb-1920", "Apr-1950", "Feb-2004", "Apr-2018"):
            self.assertAlmostEqual(corrected.loc[0, col], eto.loc[0, col] * 3, places=5)
            self.assertAlmostEqual(corrected.loc[1, col], eto.loc[1, col], places=5)
        self.assertAlmostEqual(overlap.loc[0, "Apr"], 2.0)
        self.assertAlmostEqual(full.loc[0, "Apr"], (84 + 15 * 2) / 99, places=4)
        self.assertAlmostEqual(overlap.loc[0, "Feb"], 2.0)
        self.assertAlmostEqual(full.loc[0, "Feb"], (84 + 15 * 2) / 99, places=4)

    def test_missing_overlap_month_is_rejected(self):
        eto = self.make_eto().drop(columns="Apr-2008")
        with self.assertRaisesRegex(ValueError, "must contain every month"):
            step10b.compute_hs_monthly_avg(
                eto, ["Lon", "Lat"], list(eto.columns[2:]), 2004, 2018
            )


if __name__ == "__main__":
    unittest.main()
