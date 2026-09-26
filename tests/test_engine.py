import unittest
import signal

from other_league_rankings.engine import optimal_idp_lineup_value, optimal_lineup_value, rank_league, ranking_weights, sec_ranking_weights
from other_league_rankings.models import LeagueSnapshot, LeagueTeam, MarketBundle, PlayerIdentity, ValueBook


def roster(roster_id, player_ids, wins=0, losses=0, points=0):
    return LeagueTeam(roster_id, f"u{roster_id}", f"Team {roster_id}", f"Owner {roster_id}", player_ids, [], wins, losses, 0, points)


def basic_snapshot(teams, week=1, is_superflex=False):
    return LeagueSnapshot("league", "League", 2026, week, is_superflex, 1.0, ["QB", "RB", "WR", "TE", "SUPER_FLEX"], teams)


def bundle(player_ids, dynasty_values, lineup_values):
    positions = ["QB", "RB", "WR", "TE"]
    players = {pid: PlayerIdentity(pid, pid, pid, positions[int(pid) % 4]) for pid in player_ids}
    return MarketBundle(players, [ValueBook("market", "dynasty", dynasty_values), ValueBook("starters", "lineup", lineup_values)])


class EngineTests(unittest.TestCase):
    def test_weight_schedule(self):
        self.assertEqual(ranking_weights(0), (0.45, 0.55, 0.0))
        self.assertEqual(ranking_weights(3), (0.35, 0.45, 0.20))
        self.assertEqual(ranking_weights(5), (0.30, 0.40, 0.30))
        self.assertEqual(ranking_weights(8), (0.25, 0.35, 0.40))

    def test_sec_weight_schedule_uses_approved_market_offense_results_defense_shares(self):
        self.assertEqual(sec_ranking_weights(0), (0.45, 0.55, 0.0, 0.0))
        self.assertEqual(sec_ranking_weights(3), (0.30, 0.35, 0.20, 0.15))
        self.assertEqual(sec_ranking_weights(5), (0.25, 0.32, 0.30, 0.13))
        self.assertEqual(sec_ranking_weights(8), (0.20, 0.30, 0.40, 0.10))

    def test_record_changes_ranking_as_season_weight_grows(self):
        ids = [str(i) for i in range(16)]
        teams = [roster(1, ids[:8], 5, 0, 1000), roster(2, ids[8:], 0, 5, 0)]
        dynasty = {pid: 1000 for pid in ids[:8]}
        dynasty.update({pid: 1 for pid in ids[8:]})
        lineup = {pid: 1000 for pid in ids[8:]}
        lineup.update({pid: 1 for pid in ids[:8]})
        current = rank_league(basic_snapshot(teams, week=5), bundle(ids, dynasty, lineup))

        self.assertEqual(current.teams[0].roster_id, 1)
        self.assertEqual(current.season_weight, 0.30)
        self.assertGreater(current.teams[0].season_points, current.teams[1].season_points)

    def test_record_guardrail_caps_roster_lead(self):
        ids = [str(i) for i in range(16)]
        teams = [roster(1, ids[:8], 8, 0, 1000), roster(2, ids[8:], 4, 4, 0)]
        dynasty = {pid: 1 for pid in ids[:8]}
        dynasty.update({pid: 10000 for pid in ids[8:]})
        lineup = {pid: 1 for pid in ids[:8]}
        lineup.update({pid: 10000 for pid in ids[8:]})
        result = rank_league(basic_snapshot(teams, week=9), bundle(ids, dynasty, lineup))

        by_id = {team.roster_id: team for team in result.teams}
        self.assertTrue(result.record_guardrail_active)
        self.assertTrue(by_id[2].record_guardrail_applied)
        self.assertLessEqual(by_id[2].score - by_id[1].score, 10.0)

    def test_movement_uses_previous_saturday_rank(self):
        ids = [str(i) for i in range(16)]
        teams = [roster(1, ids[:8]), roster(2, ids[8:])]
        result = rank_league(basic_snapshot(teams), bundle(ids, {pid: (1 if pid in ids[:8] else 2) for pid in ids}, {pid: (1 if pid in ids[:8] else 2) for pid in ids}), {"1": 1, "2": 2})

        by_id = {team.roster_id: team for team in result.teams}
        self.assertEqual(by_id[1].previous_rank, 1)
        self.assertEqual(by_id[1].movement, -1)

    def test_superflex_slot_is_qb_only_when_configured_as_one_qb(self):
        players = {
            "q1": PlayerIdentity("q1", "q1", "QB1", "QB"),
            "q2": PlayerIdentity("q2", "q2", "QB2", "QB"),
            "r1": PlayerIdentity("r1", "r1", "RB1", "RB"),
            "r2": PlayerIdentity("r2", "r2", "RB2", "RB"),
        }
        values = {"q1": 10, "q2": 9, "r1": 50, "r2": 40}
        players_in_roster = list(players)

        generic_sf = optimal_lineup_value(players_in_roster, ["QB", "RB", "SUPER_FLEX"], players, values, one_qb=False)
        one_qb = optimal_lineup_value(players_in_roster, ["QB", "RB", "SUPER_FLEX"], players, values, one_qb=True)

        self.assertEqual(generic_sf, 100)
        self.assertEqual(one_qb, 69)

    def test_idp_lineup_optimizer_obeys_dl_lb_db_and_idp_flex_eligibility(self):
        players = {
            "de": PlayerIdentity("de", "de", "Defensive End", "DE"),
            "dl": PlayerIdentity("dl", "dl", "Defensive Tackle", "DT"),
            "lb": PlayerIdentity("lb", "lb", "Linebacker", "LB"),
            "cb": PlayerIdentity("cb", "cb", "Cornerback", "CB"),
            "rb": PlayerIdentity("rb", "rb", "Running Back", "RB"),
        }

        value = optimal_idp_lineup_value(
            list(players), ["DL", "LB", "DB", "IDP_FLEX"], players,
            {"de": 12, "dl": 10, "lb": 11, "cb": 9, "rb": 100},
        )

        self.assertEqual(value, 42)

    def test_sec_defense_placeholder_is_zero_weight_and_does_not_change_scores(self):
        ids = [str(i) for i in range(16)]
        teams = [roster(1, ids[:8]), roster(2, ids[8:])]
        books = bundle(ids, {pid: 100 for pid in ids}, {pid: 100 for pid in ids})
        baseline = rank_league(basic_snapshot(teams), books)
        sec = basic_snapshot(teams)
        sec.idp_partial = True
        sec.defense_weight = 0.0
        result = rank_league(sec, books)

        self.assertEqual(result.defense_weight, 0.0)
        self.assertEqual([team.score for team in result.teams], [team.score for team in baseline.teams])
        self.assertEqual([team.defense_points for team in result.teams], [0.0, 0.0])

    def test_sec_defense_weight_can_be_activated_with_idp_value_book(self):
        ids = [str(i) for i in range(16)]
        teams = [roster(1, [*ids[:8], "dl1"]), roster(2, [*ids[8:], "dl2"])]
        players = {
            **{pid: PlayerIdentity(pid, pid, pid, ["QB", "RB", "WR", "TE"][int(pid) % 4]) for pid in ids},
            "dl1": PlayerIdentity("dl1", "dl1", "DL1", "DL"),
            "dl2": PlayerIdentity("dl2", "dl2", "DL2", "DL"),
        }
        snapshot = basic_snapshot([roster(1, [*ids[:8], "dl1"], 3, 2), roster(2, [*ids[8:], "dl2"], 3, 2)])
        snapshot.idp_partial = True
        snapshot.defense_weight = 0.15
        snapshot.roster_positions = ["QB", "RB", "WR", "TE", "DL"]
        books = MarketBundle(players, [
            ValueBook("market", "dynasty", {pid: 100 for pid in ids}),
            ValueBook("offense", "lineup", {pid: 100 for pid in ids}),
            ValueBook("Sleeper IDP projections", "defense", {"dl1": 20, "dl2": 1}, raw_projection=True),
        ])

        result = rank_league(snapshot, books)

        by_id = {team.roster_id: team for team in result.teams}
        self.assertAlmostEqual(result.defense_weight, 0.13)
        self.assertAlmostEqual(result.market_weight, 0.25)
        self.assertAlmostEqual(result.lineup_weight, 0.32)
        self.assertAlmostEqual(result.season_weight, 0.30)
        self.assertAlmostEqual(result.market_weight + result.lineup_weight + result.season_weight + result.defense_weight, 1.0)
        self.assertGreater(by_id[1].defense_points, by_id[2].defense_points)

    def test_sec_partial_market_signal_excludes_idp_assets(self):
        ids = ["q1", "r1", "w1", "t1", "dl1", "q2", "r2", "w2", "t2"]
        players = {
            "q1": PlayerIdentity("q1", "q1", "QB1", "QB"),
            "r1": PlayerIdentity("r1", "r1", "RB1", "RB"),
            "w1": PlayerIdentity("w1", "w1", "WR1", "WR"),
            "t1": PlayerIdentity("t1", "t1", "TE1", "TE"),
            "dl1": PlayerIdentity("dl1", "dl1", "DL1", "DL"),
            "q2": PlayerIdentity("q2", "q2", "QB2", "QB"),
            "r2": PlayerIdentity("r2", "r2", "RB2", "RB"),
            "w2": PlayerIdentity("w2", "w2", "WR2", "WR"),
            "t2": PlayerIdentity("t2", "t2", "TE2", "TE"),
        }
        snapshot = basic_snapshot([roster(1, ids[:5]), roster(2, ids[5:])], is_superflex=False)
        snapshot.idp_partial = True
        snapshot.roster_positions = ["QB", "RB", "WR", "TE", "IDP_FLEX"]
        market = {pid: 100 for pid in ids}
        market["dl1"] = 100000
        lineup = {pid: 100 for pid in ids if players[pid].position in {"QB", "RB", "WR", "TE"}}
        result = rank_league(snapshot, MarketBundle(players, [ValueBook("market", "dynasty", market), ValueBook("starters", "lineup", lineup)]))

        by_id = {team.roster_id: team for team in result.teams}
        self.assertEqual(by_id[1].market_percentile, by_id[2].market_percentile)

    def test_full_sleeper_roster_finishes_lineup_search_quickly(self):
        players = {}
        values = {}
        player_ids = []
        for position in ("QB", "RB", "WR", "TE"):
            for index in range(1, 21):
                player_id = f"{position}{index}"
                player_ids.append(player_id)
                players[player_id] = PlayerIdentity(player_id, player_id, player_id, position)
                values[player_id] = float(index)

        def timeout(_signum, _frame):
            raise TimeoutError("lineup optimizer exceeded its full-roster time budget")

        old_handler = signal.signal(signal.SIGALRM, timeout)
        signal.setitimer(signal.ITIMER_REAL, 1.0)
        try:
            score = optimal_lineup_value(
                player_ids,
                ["QB", "RB", "WR", "TE", "FLEX", "FLEX", "SUPER_FLEX"],
                players,
                values,
                one_qb=True,
            )
        except TimeoutError as exc:
            self.fail(str(exc))
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
        self.assertEqual(score, 137)

    def test_source_with_one_severely_unmapped_roster_is_not_used(self):
        ids = [str(i) for i in range(16)]
        teams = [roster(1, ids[:8]), roster(2, ids[8:])]
        players = {pid: PlayerIdentity(pid, pid, pid, ["QB", "RB", "WR", "TE"][int(pid) % 4]) for pid in ids}
        sparse = {pid: 100 for pid in ids[:8]}
        sparse[ids[8]] = 100
        books = [
            ValueBook("complete market", "dynasty", {pid: 100 for pid in ids}),
            ValueBook("sparse market", "dynasty", sparse),
            ValueBook("complete starters", "lineup", {pid: 100 for pid in ids}),
        ]

        result = rank_league(basic_snapshot(teams), MarketBundle(players, books))

        self.assertEqual(result.dynasty_sources, ["complete market"])


if __name__ == "__main__":
    unittest.main()
