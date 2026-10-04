import json
from pathlib import Path
import tempfile
import unittest

from other_league_rankings.config import load_leagues


ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_loads_six_unique_profiles(self):
        leagues = load_leagues(ROOT / "leagues.json")

        self.assertEqual(len(leagues), 6)
        self.assertEqual(len({league.league_id for league in leagues.values()}), 6)
        self.assertEqual(len({league.webhook_env for league in leagues.values()}), 6)

    def test_best_characters_and_sec_are_one_qb(self):
        leagues = load_leagues(ROOT / "leagues.json")

        self.assertEqual(leagues["best_characters"].quarterback_mode, "one_qb")
        self.assertEqual(leagues["sec"].quarterback_mode, "one_qb")

    def test_redraft_keeper_leagues_use_redraft_led_market(self):
        leagues = load_leagues(ROOT / "leagues.json")

        for key in ("broken_hearts", "rocky_top_rumble", "nine_to_five"):
            self.assertEqual(leagues[key].market_mode, "keeper_redraft")
            self.assertEqual(leagues[key].keeper_dynasty_share, 0.20)
        for key in ("best_characters", "sec", "dont_tell_my_wife"):
            self.assertEqual(leagues[key].market_mode, "dynasty")
            self.assertEqual(leagues[key].keeper_dynasty_share, 1.0)

    def test_only_sec_has_defense_schedule_enabled(self):
        leagues = load_leagues(ROOT / "leagues.json")

        self.assertEqual(leagues["sec"].defense_weight, 0.15)
        self.assertEqual(leagues["broken_hearts"].defense_weight, 0.0)

    def test_duplicate_league_ids_are_rejected(self):
        theme = {
            "background": "#000000",
            "panel": "#111111",
            "text": "#EEEEEE",
            "muted": "#888888",
            "market": "#CCAA00",
            "lineup": "#BB3344",
            "season": "#4477AA",
            "accent": "#FFFFFF",
        }
        raw = {
            "leagues": {
                "one": {"league_id": "same", "webhook_env": "ONE", "name": "One", "theme": theme},
                "two": {"league_id": "same", "webhook_env": "TWO", "name": "Two", "theme": theme},
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "leagues.json"
            path.write_text(json.dumps(raw), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "duplicate league_id"):
                load_leagues(path)


if __name__ == "__main__":
    unittest.main()
