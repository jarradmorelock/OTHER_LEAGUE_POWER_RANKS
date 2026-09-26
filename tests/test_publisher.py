import tempfile
import unittest
from pathlib import Path

from other_league_rankings.config import load_leagues
from other_league_rankings.models import LeagueSnapshot, LeagueTeam, RankedTeam, RankingResult
from other_league_rankings.publisher import PublishError, publish_league
from other_league_rankings.state import StateStore


LEAGUES = load_leagues(Path(__file__).resolve().parents[1] / "leagues.json")


def result():
    snapshot = LeagueSnapshot("1341161857683058688", "SEC", 2026, 3, False, 1.0, ["QB"], [
        LeagueTeam(1, "u1", "One", "Owner", [], [], 2, 1, 0, 300),
        LeagueTeam(2, "u2", "Two", "Owner", [], [], 1, 2, 0, 250),
    ], idp_partial=True)
    teams = [
        RankedTeam(1, 1, "One", "Owner", "2-1", 300, 80, 70, 90, 50, 20, 30, 15, 40),
        RankedTeam(2, 2, "Two", "Owner", "1-2", 250, 50, 60, 55, 40, 20, 25, 5, 30),
    ]
    return RankingResult(snapshot, teams, ["Dynasty Daddy"], ["ROS"], True, "2026-09-25T12:00:00Z", 0.3, 0.35, 0.2, False, defense_weight=0.15, defense_sources=["Sleeper IDP weekly projections (raw pts_ppr)"])


class FakeDiscord:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def post_forum(self, *args):
        self.calls.append(args)
        if self.fail:
            raise RuntimeError("discord unavailable")
        return {"id": "post-1"}


class PublisherTests(unittest.TestCase):
    def test_dry_run_never_calls_webhook_or_changes_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = StateStore(Path(temp_dir) / "state")
            discord = FakeDiscord()
            outcome = publish_league(LEAGUES["sec"], result(), (Path("a"), Path("b")), state, dry_run=True, webhook_url="https://discord.com/api/webhooks/1/token", discord=discord)
            self.assertEqual(outcome.status, "dry_run")
            self.assertEqual(discord.calls, [])
            self.assertEqual(state.load("sec").rank_by_roster_id, {})

    def test_same_week_post_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = StateStore(Path(temp_dir) / "state")
            state.save_success("sec", result(), "2026-week-3")
            discord = FakeDiscord()
            outcome = publish_league(LEAGUES["sec"], result(), (Path("a"), Path("b")), state, dry_run=False, webhook_url="https://discord.com/api/webhooks/1/token", discord=discord)
            self.assertEqual(outcome.status, "skipped")
            self.assertEqual(discord.calls, [])

    def test_failure_does_not_advance_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = StateStore(Path(temp_dir) / "state")
            with self.assertRaises(PublishError):
                publish_league(LEAGUES["sec"], result(), (Path("a"), Path("b")), state, dry_run=False, webhook_url="https://discord.com/api/webhooks/1/token", discord=FakeDiscord(fail=True))
            self.assertEqual(state.load("sec").rank_by_roster_id, {})

    def test_success_posts_both_graphs_with_raw_idp_disclosure_and_weight_mix_then_saves(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = StateStore(Path(temp_dir) / "state")
            discord = FakeDiscord()
            outcome = publish_league(LEAGUES["sec"], result(), (Path("ranks.png"), Path("odds.png")), state, dry_run=False, webhook_url="https://discord.com/api/webhooks/1/token", discord=discord)
            self.assertEqual(outcome.status, "posted")
            self.assertIn("Sleeper's raw weekly `pts_ppr`", discord.calls[0][2])
            self.assertIn("custom SEC IDP scoring and bonuses are not applied", discord.calls[0][2])
            self.assertIn("30% market / 35% offense / 15% defense / 20% season results", discord.calls[0][2])
            self.assertEqual(state.load("sec").last_post_key, "2026-week-3")


if __name__ == "__main__":
    unittest.main()
