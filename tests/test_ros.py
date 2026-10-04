import unittest

from other_league_rankings.models import LeagueSnapshot, LeagueTeam, PlayerIdentity
from other_league_rankings.ros import fetch_ros_team_values, projection_fantasy_points


class RosProjectionTests(unittest.TestCase):
    def test_scores_league_specific_stats_and_bonuses(self):
        scoring = {
            "pass_yd": 0.04,
            "pass_td": 6.0,
            "pass_int": -2.0,
            "pass_cmp": 0.10,
            "rush_yd": 0.10,
            "rush_att": 0.10,
            "rush_fd": 0.25,
            "rec": 0.5,
            "rec_yd": 0.10,
            "rec_fd": 0.25,
            "bonus_rec_yd_100": 1.5,
        }
        projection = {
            "stats": {
                "pass_yd": 250,
                "pass_td": 2,
                "pass_int": 1,
                "pass_cmp": 22,
                "rush_yd": 30,
                "rush_att": 5,
                "rush_fd": 2,
                "rec": 4,
                "rec_yd": 105,
                "rec_fd": 3,
            }
        }
        self.assertAlmostEqual(
            projection_fantasy_points(projection, scoring, position="WR"),
            40.95,
        )

    def test_te_reception_bonus_is_position_aware(self):
        scoring = {"rec": 0.5, "bonus_rec_te": 0.5}
        projection = {"stats": {"rec": 6}}
        self.assertEqual(
            projection_fantasy_points(projection, scoring, position="TE"),
            6.0,
        )
        self.assertEqual(
            projection_fantasy_points(projection, scoring, position="WR"),
            3.0,
        )

    def test_ros_average_reoptimizes_legal_lineup_each_week(self):
        teams = [
            LeagueTeam(1, "u1", "One", "One", ["a", "b"], [], 1, 0, 0, 100),
            LeagueTeam(2, "u2", "Two", "Two", ["c"], [], 0, 1, 0, 80),
        ]
        snapshot = LeagueSnapshot(
            "league",
            "League",
            2026,
            16,
            False,
            0.5,
            ["RB"],
            teams,
            scoring_settings={"rush_yd": 0.1},
            playoff_week_start=15,
        )
        players = {
            "a": PlayerIdentity("a", "a", "A", "RB"),
            "b": PlayerIdentity("b", "b", "B", "RB"),
            "c": PlayerIdentity("c", "c", "C", "RB"),
        }

        class Client:
            def get_json(self, url):
                if url.endswith("/16"):
                    return {
                        "a": {"stats": {"rush_yd": 100}},
                        "b": {"stats": {"rush_yd": 40}},
                        "c": {"stats": {"rush_yd": 80}},
                    }
                if url.endswith("/17"):
                    return {
                        "a": {"stats": {"rush_yd": 20}},
                        "b": {"stats": {"rush_yd": 120}},
                        "c": {"stats": {"rush_yd": 90}},
                    }
                return {}

        values, weeks, warnings = fetch_ros_team_values(Client(), snapshot, players)

        self.assertEqual(weeks, [16, 17])
        self.assertAlmostEqual(values[1], 11.0)
        self.assertAlmostEqual(values[2], 8.5)
        self.assertFalse(any("insufficient" in warning.lower() for warning in warnings))


if __name__ == "__main__":
    unittest.main()
