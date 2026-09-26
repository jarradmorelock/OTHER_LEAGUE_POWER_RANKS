"""Independent per-league orchestration with failure isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import load_leagues
from .engine import rank_league
from .forecast import attach_forecast
from .http import HttpClient
from .models import LeagueConfig, RankingResult
from .publisher import publish_league
from .render import render_result
from .sleeper import fetch_snapshot
from .sources import fetch_rankings
from .state import StateStore


@dataclass
class LeagueRunStatus:
    league_key: str
    state: str
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    result: RankingResult | None = None


@dataclass
class RunSummary:
    statuses: dict[str, LeagueRunStatus]


class DefaultServices:
    def __init__(self) -> None:
        self.client = HttpClient()

    def fetch_snapshot(self, client, config, week=None):
        return fetch_snapshot(client, config, week)

    def fetch_rankings(self, client, config, snapshot):
        return fetch_rankings(client, config, snapshot)

    def render_result(self, result, config, output_dir):
        return render_result(result, config, output_dir)

    def publish_league(self, config, result, paths, state, dry_run, force=False):
        return publish_league(config, result, paths, state, dry_run, force=force)


def run(
    configs: dict[str, LeagueConfig] | None = None,
    selected: str = "all",
    dry_run: bool = True,
    force: bool = False,
    week: int | None = None,
    *,
    output_dir: Path = Path("exports"),
    state: StateStore | None = None,
    services: Any = None,
) -> RunSummary:
    configs = configs or load_leagues(Path(__file__).resolve().parents[1] / "leagues.json")
    if selected == "all":
        chosen = configs
    elif selected in configs:
        chosen = {selected: configs[selected]}
    else:
        raise ValueError(f"Unknown league selection: {selected}")
    services = services or DefaultServices()
    client = getattr(services, "client", None)
    state = state or StateStore(Path("state"))
    statuses: dict[str, LeagueRunStatus] = {}
    for key, config in chosen.items():
        try:
            history = state.load(key)
            snapshot = services.fetch_snapshot(client, config, week)
            bundle = services.fetch_rankings(client, config, snapshot)
            result = rank_league(snapshot, bundle, history.rank_by_roster_id)
            attach_forecast(result)
            paths = services.render_result(result, config, Path(output_dir) / key)
            published = services.publish_league(config, result, paths, state, dry_run, force=force)
            statuses[key] = LeagueRunStatus(
                key,
                published.status,
                "",
                list(result.warnings),
                result,
            )
        except Exception as exc:
            message = _safe_error(exc)
            statuses[key] = LeagueRunStatus(key, "failed", message)
    return RunSummary(statuses)


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    # Webhook URLs contain bearer-like tokens; never echo URL-looking strings.
    if "webhook" in message.lower() or "discord.com/api" in message.lower():
        return f"{type(exc).__name__}: publication or configuration error (sensitive endpoint hidden)"
    return f"{type(exc).__name__}: {message[:300]}"
