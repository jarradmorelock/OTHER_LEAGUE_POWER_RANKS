import unittest

from other_league_rankings.config import load_leagues
from other_league_rankings.sleeper import fetch_snapshot, normalize_snapshot_payloads


LEAGUES = load_leagues(__import__("pathlib").Path(__file__).resolve().parents[1] / "leagues.json")


def payloads(league_key="sec", roster_positions=None, scoring_settings=None, rosters=None):
    config = LEAGUES[league_key]
    league = {
        "league_id": config.league_id,
        "name": config.name,
        "season": "2026",
        "status": "in_season",
        "roster_positions": roster_positions or ["QB", "RB", "WR", "TE", "SUPER_FLEX", "DL", "LB", "DB", "IDP_FLEX"],
        "scoring_settings": scoring_settings or {"rec": 1.0, "bonus_rec_te": 1.5, "idp_sack": 5.0, "idp_def_td": 7.0},
        "settings": {"leg": 3, "playoff_week_start": 15, "playoff_teams": 6, "divisions": 2, "playoff_round_type": 0},
    }
    rosters = rosters if rosters is not None else [
        {"roster_id": 1, "owner_id": "u1", "players": ["p1", "p2"], "settings": {"wins": 2, "losses": 0, "ties": 1, "fpts": 300, "fpts_decimal": 25, "division": 1}},
        {"roster_id": 2, "owner_id": "u2", "players": ["p3"], "settings": {"wins": 1, "losses": 2, "ties": 0, "fpts": 250, "fpts_decimal": 75, "division": 2}},
    ]
    users = [
        {"user_id": "u1", "display_name": "Owner One", "metadata": {"team_name": "Team One"}},
        {"user_id": "u2", "username": "owner2"},
    ]
    return config, league, users, rosters


class SleeperTests(unittest.TestCase):
    def test_fetch_snapshot_uses_injected_client_and_includes_future_schedule(self):
        config, league, users, rosters = payloads("best_characters", ["QB", "SUPER_FLEX"], {"rec": 1.0, "bonus_rec_te": 0.5})

        class Client:
            def get_json(self, url):
                if url.endswith("/users"):
                    return users
                if url.endswith("/rosters"):
                    return rosters
                if url.endswith("/traded_picks"):
                    return []
                if url.endswith("/state/nfl"):
                    return {"season": "2026", "week": 3}
                if url.endswith("/winners_bracket"):
                    return []
                if url.endswith("/matchups/3"):
                    return [{"matchup_id": 1, "roster_id": 1, "points": 0}, {"matchup_id": 1, "roster_id": 2, "points": 0}]
                if "/matchups/" in url:
                    return []
                return league

        snapshot = fetch_snapshot(Client(), config)
        self.assertEqual(snapshot.week, 3)
        self.assertEqual(len(snapshot.matchups), 1)
        self.assertEqual(snapshot.matchups[0].week, 3)

    def test_keeps_all_sec_scoring_keys(self):
        config, league, users, rosters = payloads()
        snapshot = normalize_snapshot_payloads(config, league, users, rosters, [], {"season": "2026", "week": 3}, [], [])

        self.assertEqual(snapshot.scoring_settings["idp_sack"], 5.0)
        self.assertEqual(snapshot.scoring_settings["bonus_rec_te"], 1.5)
        self.assertIn("idp_def_td", snapshot.scoring_settings)

    def test_best_characters_superflex_slot_is_preserved(self):
        config, league, users, rosters = payloads("best_characters", ["RB", "WR", "TE", "FLEX", "SUPER_FLEX"] * 2, {"rec": 1.0, "bonus_rec_te": 0.5})
        snapshot = normalize_snapshot_payloads(config, league, users, rosters, [], {"season": "2026", "week": 4}, [], [])

        self.assertIn("SUPER_FLEX", snapshot.roster_positions)
        self.assertFalse(snapshot.is_superflex)

    def test_normalizes_records_and_owners(self):
        config, league, users, rosters = payloads()
        snapshot = normalize_snapshot_payloads(config, league, users, rosters, [], {"season": "2026", "week": 3}, [], [])

        self.assertEqual(snapshot.teams[0].record, "2-0-1")
        self.assertEqual(snapshot.teams[0].points_for, 300.25)
        self.assertEqual(snapshot.teams[0].owner_name, "Owner One")
        self.assertEqual(snapshot.teams[0].team_name, "Team One")

    def test_rejects_missing_rosters(self):
        config, league, users, _ = payloads()
        with self.assertRaisesRegex(ValueError, "rosters"):
            normalize_snapshot_payloads(config, league, users, [], [], {"season": "2026", "week": 3}, [], [])

    def test_scoring_mismatch_is_reported(self):
        config, league, users, rosters = payloads("best_characters", ["QB", "SUPER_FLEX"], {"rec": 1.0, "bonus_rec_te": 0.0})
        snapshot = normalize_snapshot_payloads(config, league, users, rosters, [], {"season": "2026", "week": 3}, [], [])

        self.assertTrue(any("bonus_rec_te" in warning for warning in snapshot.warnings))

    def test_bench_slots_are_not_reported_as_unsupported_starters(self):
        config, league, users, rosters = payloads("best_characters", ["QB", "SUPER_FLEX", "BN"], {"rec": 1.0, "bonus_rec_te": 0.5})
        snapshot = normalize_snapshot_payloads(config, league, users, rosters, [], {"season": "2026", "week": 3}, [], [])
        self.assertFalse(any("BN" in warning for warning in snapshot.warnings))


if __name__ == "__main__":
    unittest.main()
