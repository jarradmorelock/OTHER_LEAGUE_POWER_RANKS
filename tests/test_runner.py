import tempfile
import unittest
from pathlib import Path

from other_league_rankings.config import load_leagues
from other_league_rankings.models import LeagueSnapshot, LeagueTeam, MarketBundle, PlayerIdentity, ValueBook
from other_league_rankings.runner import run
from other_league_rankings.state import StateStore


LEAGUES = load_leagues(Path(__file__).resolve().parents[1] / "leagues.json")


def snapshot(config):
    players = [str(i) for i in range(8)]
    return LeagueSnapshot(config.league_id, config.name, 2026, 2, False, 1.0, ["QB", "RB", "WR", "TE"], [
        LeagueTeam(1, "u1", "One", "Owner", players[:4], [], 1, 0, 0, 100),
        LeagueTeam(2, "u2", "Two", "Owner", players[4:], [], 0, 1, 0, 80),
    ])


def bundle():
    ids = [str(i) for i in range(8)]
    positions = ["QB", "RB", "WR", "TE"]
    players = {pid: PlayerIdentity(pid, pid, pid, positions[int(pid) % 4]) for pid in ids}
    return MarketBundle(players, [ValueBook("market", "dynasty", {pid: int(pid)+1 for pid in ids}), ValueBook("ROS", "lineup", {pid: int(pid)+1 for pid in ids})])


class FakeServices:
    def __init__(self):
        self.fail = set()
        self.published = []
        self.rendered = []

    def fetch_snapshot(self, client, config, week=None):
        if config.key in self.fail:
            raise RuntimeError("snapshot failure")
        return snapshot(config)

    def fetch_rankings(self, client, config, league_snapshot):
        return bundle()

    def render_result(self, result, config, output_dir):
        self.rendered.append((result, config, output_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        return (output_dir / "rank.png", output_dir / "odds.png")

    def publish_league(self, config, result, paths, state, dry_run, force=False):
        self.published.append((config.key, dry_run))
        return type("Outcome", (), {"status": "dry_run" if dry_run else "posted"})()


class RunnerTests(unittest.TestCase):
    def test_dry_run_never_calls_webhook(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            services = FakeServices()
            summary = run({"sec": LEAGUES["sec"]}, selected="all", dry_run=True, output_dir=Path(temp_dir) / "exports", state=StateStore(Path(temp_dir) / "state"), services=services)
            self.assertEqual(summary.statuses["sec"].state, "dry_run")
            self.assertEqual(services.published, [("sec", True)])

    def test_failed_league_does_not_stop_batch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            services = FakeServices()
            services.fail.add("sec")
            configs = {"sec": LEAGUES["sec"], "best_characters": LEAGUES["best_characters"]}
            summary = run(configs, selected="all", dry_run=False, output_dir=Path(temp_dir) / "exports", state=StateStore(Path(temp_dir) / "state"), services=services)
            self.assertEqual(summary.statuses["sec"].state, "failed")
            self.assertEqual(summary.statuses["best_characters"].state, "posted")

    def test_single_league_selection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            services = FakeServices()
            summary = run(LEAGUES, selected="sec", dry_run=True, output_dir=Path(temp_dir) / "exports", state=StateStore(Path(temp_dir) / "state"), services=services)
            self.assertEqual(list(summary.statuses), ["sec"])
            self.assertEqual(len(services.rendered), 1)


if __name__ == "__main__":
    unittest.main()
