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

    def test_tuesday_saturday_tuesday_chain_preserves_movement_and_archive(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir))
            start = result()
            start.generated_at = "2026-10-10T16:00:00+00:00"
            store.save_success("sec", start, "2026-week-5")
            tuesday = result()
            tuesday.generated_at = "2026-10-13T15:00:00+00:00"
            tuesday.teams[0].rank = 3
            tuesday.teams[1].rank = 1
            store.save_rank_history_only("sec", tuesday)
            self.assertEqual(store.load("sec").last_post_key, "2026-week-5")
            self.assertEqual(store.load("sec").rank_by_roster_id["11"], 3)
            saturday = result()
            saturday.generated_at = "2026-10-17T16:00:00+00:00"
            saturday.teams[0].rank = 5
            saturday.teams[1].rank = 1
            store.save_success("sec", saturday, "2026-week-6")
            self.assertEqual(store.load("sec").rank_by_roster_id["11"], 5)
            archive = sorted((Path(temp_dir) / "history" / "sec").glob("*.json"))
            self.assertEqual(len(archive), 3)
            snapshots = [__import__("json").loads(p.read_text()) for p in archive]
            self.assertEqual([entry["publication"] for entry in snapshots],
                             ["discord", "editorial", "discord"])
            self.assertEqual(snapshots[2]["previous_rank_by_roster_id"]["11"], 3)
            team = next(t for t in snapshots[2]["teams"] if t["roster_id"] == 11)
            self.assertEqual(team["movement"], -2)
            stale = result()
            stale.generated_at = "2026-10-13T15:00:00+00:00"
            with self.assertRaisesRegex(ValueError, "stale"):
                store.save_rank_history_only("sec", stale)
            self.assertEqual(len(list((Path(temp_dir) / "history" / "sec").glob("*.json"))), 3)
            self.assertEqual(store.load("sec").rank_by_roster_id["11"], 5)

    def test_missing_state_is_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(StateStore(Path(temp_dir)).load("sec"), LeagueState())

    def test_invalid_league_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "league key"):
                StateStore(Path(temp_dir)).load("../sec")


if __name__ == "__main__":
    unittest.main()
