import unittest

from other_league_rankings.forecast import attach_forecast
from other_league_rankings.models import LeagueSnapshot, LeagueTeam, RankedTeam, RankingResult


def make_result(*, week=2, bracket=None):
    teams = [
        LeagueTeam(1, "u1", "One", "Owner 1", [], [], 2, 0, 0, 200, division=1),
        LeagueTeam(2, "u2", "Two", "Owner 2", [], [], 1, 1, 0, 180, division=1),
        LeagueTeam(3, "u3", "Three", "Owner 3", [], [], 0, 2, 0, 150, division=2),
        LeagueTeam(4, "u4", "Four", "Owner 4", [], [], 0, 2, 0, 130, division=2),
    ]
    snapshot = LeagueSnapshot(
        "league", "League", 2026, week, False, 1.0, ["QB"], teams,
        start_week=1, playoff_week_start=15, playoff_teams=2, divisions=1,
        playoff_bracket=bracket or [],
    )
    ranked = [
        RankedTeam(i, team.roster_id, team.team_name, team.owner_name, team.record, team.points_for, 100-i, 50, 50, None, 0, 0, 0, 100-i)
        for i, team in enumerate(teams, start=1)
    ]
    return RankingResult(snapshot, ranked, ["market"], ["ROS"], True, "2026-09-25T12:00:00+00:00", 0.3, 0.4, 0.3, False)


class ForecastTests(unittest.TestCase):
    def test_forecast_is_repeatable(self):
        result = make_result()
        attach_forecast(result, simulations=300)
        first = [(team.make_playoffs_pct, team.win_championship_pct) for team in result.teams]
        attach_forecast(result, simulations=300)
        self.assertEqual(first, [(team.make_playoffs_pct, team.win_championship_pct) for team in result.teams])

    def test_playoff_odds_stay_between_zero_and_one_hundred(self):
        result = make_result()
        attach_forecast(result, simulations=300)
        for team in result.teams:
            self.assertGreaterEqual(team.make_playoffs_pct, 0)
            self.assertLessEqual(team.make_playoffs_pct, 100)
            self.assertGreaterEqual(team.win_championship_pct, 0)
            self.assertLessEqual(team.win_championship_pct, 100)

    def test_playoff_odds_are_monotonic_for_two_team_fixture(self):
        result = make_result()
        result.league.playoff_teams = 2
        attach_forecast(result, simulations=300)
        by_id = {team.roster_id: team for team in result.teams}
        self.assertGreaterEqual(by_id[1].make_playoffs_pct, by_id[4].make_playoffs_pct)

    def test_active_bracket_excludes_eliminated_teams_from_title_path(self):
        bracket = [
            {"r": 1, "t1": 1, "t2": 2, "w": 1, "l": 2},
            {"r": 1, "t1": 3, "t2": 4, "w": 3, "l": 4},
        ]
        result = make_result(week=16, bracket=bracket)
        attach_forecast(result, simulations=300)
        by_id = {team.roster_id: team for team in result.teams}
        for eliminated in (2, 4):
            self.assertEqual(by_id[eliminated].win_championship_pct, 0)
            self.assertEqual(by_id[eliminated].make_final_pct, 0)


if __name__ == "__main__":
    unittest.main()
