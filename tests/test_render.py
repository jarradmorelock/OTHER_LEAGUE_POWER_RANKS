import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

from other_league_rankings.config import load_leagues
from other_league_rankings.models import LeagueSnapshot, LeagueTeam, RankedTeam, RankingResult
from other_league_rankings.render import _footer, render_result


LEAGUES = load_leagues(Path(__file__).resolve().parents[1] / "leagues.json")


def make_result(partial=False):
    snapshot = LeagueSnapshot("1341161857683058688", "SEC", 2026, 3, False, 1.0, ["QB"], [
        LeagueTeam(1, "u1", "Offense One", "Owner One", [], [], 2, 1, 0, 300),
        LeagueTeam(2, "u2", "Offense Two", "Owner Two", [], [], 1, 2, 0, 250),
    ], idp_partial=partial)
    teams = [
        RankedTeam(1, 1, "Offense One", "Owner One", "2-1", 300, 80, 70, 90, 50, 20, 30, 15, 40, previous_rank=2, movement=1, make_playoffs_pct=90, win_championship_pct=60),
        RankedTeam(2, 2, "Offense Two", "Owner Two", "1-2", 250, 50, 60, 55, 40, 20, 25, 5, 30, previous_rank=1, movement=-1, make_playoffs_pct=50, win_championship_pct=20),
    ]
    return RankingResult(snapshot, teams, ["DynastyDaddy"], ["ROS"], True, "2026-09-25T12:00:00+00:00", 0.3, 0.35, 0.2, False, forecast_simulations=100, forecast_model="ROS starters", defense_weight=0.15, defense_sources=["Sleeper IDP weekly projections (raw pts_ppr)"])


@unittest.skipUnless(importlib.util.find_spec("matplotlib"), "matplotlib not installed in local environment")
class RenderTests(unittest.TestCase):
    def test_render_writes_two_gallery_pngs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = render_result(make_result(), LEAGUES["sec"], Path(temp_dir))

            self.assertEqual(len(paths), 2)
            for path in paths:
                data = path.read_bytes()
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                width, height = struct.unpack(">II", data[16:24])
                self.assertGreaterEqual(width, 1000)
                self.assertGreaterEqual(height, 1000)

    def test_sec_idp_projection_disclosure_is_in_both_png_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = render_result(make_result(partial=True), LEAGUES["sec"], Path(temp_dir))

            self.assertTrue(all("RAW SLEEPER PTS_PPR" in path.read_bytes().decode("latin-1") for path in paths))

    def test_sec_chart_names_offense_and_includes_weighted_defense_component(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = render_result(make_result(partial=True), LEAGUES["sec"], Path(temp_dir))

            ranking_metadata = paths[0].read_bytes().decode("latin-1")
            self.assertIn("Offense", ranking_metadata)
            self.assertIn("Defense", ranking_metadata)
            self.assertIn("15% weight", ranking_metadata.lower())

    def test_source_footer_does_not_repeat_long_sec_disclosure(self):
        import matplotlib.pyplot as plt

        figure = plt.figure()
        result = make_result(partial=True)
        _footer(figure, result, LEAGUES["sec"].theme, "weight details")

        self.assertNotIn("IDP INCLUDED", figure.texts[-1].get_text())
        plt.close(figure)


if __name__ == "__main__":
    unittest.main()
