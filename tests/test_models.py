import unittest

from other_league_rankings.models import LeagueTeam


class ModelTests(unittest.TestCase):
    def test_tied_record_counts_as_half_win(self):
        team = LeagueTeam(
            roster_id=1,
            owner_id="owner",
            team_name="Team",
            owner_name="Owner",
            player_ids=[],
            picks=[],
            wins=2,
            losses=1,
            ties=1,
            points_for=10.0,
        )

        self.assertEqual(team.games, 4)
        self.assertEqual(team.record, "2-1-1")
        self.assertEqual(team.win_percentage, 0.625)


if __name__ == "__main__":
    unittest.main()
