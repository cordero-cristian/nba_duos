import unittest
from unittest.mock import patch

import pandas as pd

import main


class FetchDuosTests(unittest.TestCase):
    def test_fetch_duos_retries_then_succeeds(self):
        fake_df = pd.DataFrame([{"GROUP_ID": "1", "POSS": 1000, "MIN": 400}])

        class FakeResponse:
            def get_data_frames(self):
                return [fake_df]

        side_effects = [Exception("timeout"), Exception("timeout"), FakeResponse()]

        with patch("main.LeagueDashLineups", side_effect=side_effects) as mock_ctor, patch("main.time.sleep"):
            df = main.fetch_duos(season="2025-26")

        self.assertEqual(len(df), 1)
        self.assertEqual(mock_ctor.call_count, 3)

    def test_fetch_duos_raises_after_max_retries(self):
        with patch("main.LeagueDashLineups", side_effect=Exception("api down")), patch("main.time.sleep"):
            with self.assertRaises(RuntimeError) as cm:
                main.fetch_duos(season="2025-26")

        self.assertIn("Failed to fetch NBA duo data", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
