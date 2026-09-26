import tempfile
import unittest
from pathlib import Path

from other_league_rankings.models import RankedTeam, RankingResult
from other_league_rankings.state import LeagueState, StateStore


def result():
    return RankingResult(None, [
        RankedTeam(1, 11, "One", "Owner", "1-0", 100, 90, 90, 90, 50, 30, 40, 20, 80),
        RankedTeam(2, 22, "Two", "Owner", "0-1", 80, 10, 10, 10, 50, 5, 5, 0, 10),
    ], ["Market"], ["ROS"], True, "2026-09-25T12:00:00+00:00", 0.3, 0.4, 0.3, False)


class StateTests(unittest.TestCase):
    def test_state_paths_are_isolated_by_league(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir))
            self.assertNotEqual(store.path_for("sec"), store.path_for("best_characters"))

    def test_previous_ranks_are_loaded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir))
            store.save_success("sec", result(), "2026-week-3")
            state = store.load("sec")
            self.assertEqual(state.rank_by_roster_id, {"11": 1, "22": 2})
            self.assertEqual(state.last_post_key, "2026-week-3")

    def test_missing_state_is_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(StateStore(Path(temp_dir)).load("sec"), LeagueState())

    def test_invalid_league_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "league key"):
                StateStore(Path(temp_dir)).load("../sec")


if __name__ == "__main__":
    unittest.main()
