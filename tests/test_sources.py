import unittest

from pathlib import Path

from other_league_rankings.config import load_leagues
from other_league_rankings.http import DataSourceError
from other_league_rankings.models import LeagueSnapshot, LeagueTeam, PlayerIdentity
from other_league_rankings.sources import fetch_rankings, fetch_sleeper_idp_projections, parse_pick_asset


LEAGUES = load_leagues(Path(__file__).resolve().parents[1] / "leagues.json")
METADATA = [
    {
        "name_id": f"player{i}",
        "full_name": f"Player {i}",
        "sleeper_id": str(i),
        "position": ["QB", "RB", "WR", "TE"][i % 4],
        "avg_adp": 100 + i,
        "avg_ros": 10 + i,
        "injury_status": "",
    }
    for i in range(101)
]


def make_snapshot(config):
    return LeagueSnapshot(
        league_id=config.league_id,
        league_name=config.name,
        season=2026,
        week=3,
        is_superflex=False,
        ppr=1.0,
        roster_positions=["QB", "RB", "WR", "TE"],
        teams=[LeagueTeam(1, "u1", "One", "Owner", ["0", "1"], [], 1, 1, 0, 200.0)],
    )


class FakeClient:
    def __init__(self, primary=True):
        self.primary = primary
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        if "/projections/nfl/regular/" in url:
            return {}
        if "dynasty-daddy.com" in url:
            if not self.primary:
                raise DataSourceError("primary unavailable")
            if url.endswith("/today"):
                return METADATA
            return [{"name_id": f"player{i}", "trade_value": 1000 - i, "sf_trade_value": 900 - i} for i in range(101)]
        if "fantasycalc.com" in url:
            return [
                {"value": 1000 - i, "player": {"sleeperId": str(i), "name": f"Player {i}", "position": "RB"}}
                for i in range(101)
            ]
        raise AssertionError(url)


class SourceTests(unittest.TestCase):
    def test_sec_warnings_do_not_claim_idp_is_excluded(self):
        config = LEAGUES["sec"]
        bundle = fetch_rankings(FakeClient(), config, make_snapshot(config))

        self.assertFalse(any("IDP_NOT_INCLUDED" in warning for warning in bundle.warnings))

    def test_sleeper_idp_projection_uses_raw_provider_pts_ppr_not_sec_scoring_rules(self):
        config = LEAGUES["sec"]
        snapshot = make_snapshot(config)
        snapshot.scoring_settings = {
            "idp_tkl_solo": 2.0,
            "idp_sack": 5.0,
            "bonus_sack_2p": 3.0,
        }
        players = {"dl1": PlayerIdentity("dl1", "edge", "Defender One", "DL")}

        class ProjectionClient:
            def get_json(self, url):
                self.url = url
                return {"dl1": {"gp": 1, "pts_ppr": 7.75, "idp_tkl_solo": 4, "idp_sack": 0.5}}

        book, warnings = fetch_sleeper_idp_projections(ProjectionClient(), snapshot, players)

        self.assertEqual(book.player_values["dl1"], 7.75)
        self.assertFalse(book.scoring_adjusted)
        self.assertTrue(book.raw_projection)
        self.assertTrue(any("pts_ppr" in warning.lower() for warning in warnings))
        self.assertFalse(any("bonus_sack_2p" in warning for warning in warnings))

    def test_maps_market_values_to_sleeper_ids(self):
        config = LEAGUES["sec"]
        bundle = fetch_rankings(FakeClient(), config, make_snapshot(config))

        self.assertEqual(bundle.players["0"].full_name, "Player 0")
        self.assertGreaterEqual(len(bundle.dynasty_books), 1)
        self.assertIn("0", bundle.dynasty_books[0].player_values)

    def test_ros_is_a_lineup_signal(self):
        config = LEAGUES["sec"]
        bundle = fetch_rankings(FakeClient(), config, make_snapshot(config))

        self.assertIn("0", bundle.lineup_books[0].player_values)
        self.assertGreater(bundle.lineup_books[0].player_values["0"], 450)

    def test_falls_back_to_fantasycalc_when_primary_feed_missing(self):
        config = LEAGUES["sec"]
        bundle = fetch_rankings(FakeClient(primary=False), config, make_snapshot(config))

        self.assertTrue(any("FantasyCalc" in warning for warning in bundle.warnings))
        self.assertGreaterEqual(len(bundle.dynasty_books), 1)
        self.assertGreaterEqual(len(bundle.lineup_books), 1)

    def test_generic_rank_warns_for_te_premium(self):
        config = LEAGUES["best_characters"]
        bundle = fetch_rankings(FakeClient(), config, make_snapshot(config))

        self.assertTrue(any("TE premium" in warning for warning in bundle.warnings))
        self.assertFalse(bundle.lineup_books[0].scoring_adjusted)

    def test_sleeper_catalog_identifies_rostered_idp_without_assigning_value(self):
        config = LEAGUES["sec"]
        league_snapshot = make_snapshot(config)
        league_snapshot.teams[0].player_ids.append("defender")

        class CatalogClient(FakeClient):
            def get_json(self, url):
                if url == "https://api.sleeper.app/v1/players/nfl":
                    return {"defender": {"first_name": "Defensive", "last_name": "Player", "position": "DL"}}
                return super().get_json(url)

        bundle = fetch_rankings(CatalogClient(), config, league_snapshot)
        self.assertEqual(bundle.players["defender"].position, "DL")
        self.assertTrue(all("defender" not in book.player_values for book in bundle.books))

    def test_redraft_fallback_survives_unavailable_fantasycalc_dynasty_feed(self):
        config = LEAGUES["sec"]

        class RedraftOnlyFallbackClient(FakeClient):
            def get_json(self, url):
                if url.endswith("/today"):
                    return [{**row, "avg_ros": 0} for row in METADATA]
                if "fantasycalc.com" in url and "isDynasty=true" in url:
                    raise DataSourceError("dynasty fallback unavailable")
                return super().get_json(url)

        bundle = fetch_rankings(RedraftOnlyFallbackClient(), config, make_snapshot(config))
        self.assertGreaterEqual(len(bundle.dynasty_books), 1)
        self.assertTrue(any(book.name == "FantasyCalc Redraft Direct" for book in bundle.lineup_books))

    def test_pick_parser_normalizes_market_assets(self):
        self.assertEqual(parse_pick_asset("2027 Mid 1st"), (2027, "mid", 1))


if __name__ == "__main__":
    unittest.main()
