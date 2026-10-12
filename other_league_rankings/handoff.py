"""Magazine-ready authoritative rankings feed for the six other leagues."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .models import LeagueConfig, RankingResult

PUBLICATION_KEYS = {
    "broken_hearts": "ballad_crier",
    "rocky_top_rumble": "volunteer_voice",
    "nine_to_five": "the_stampede",
    "best_characters": "hollywood_beat",
    "sec": "saturday_standard",
    "dont_tell_my_wife": "dont_tell_my_wife",
}


def write_editorial_handoff(
    config: LeagueConfig, result: RankingResult,
    images: tuple[Path, Path], output_root: Path,
) -> Path:
    publication_key = PUBLICATION_KEYS[config.key]
    output_root = Path(output_root)
    assets = output_root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for label, original in zip(("power_rankings", "playoff_forecast"), images):
        filename = f"{publication_key}-{'power-rankings' if label == 'power_rankings' else 'playoff-forecast'}.png"
        destination = assets / filename
        shutil.copyfile(original, destination)
        manifest[label] = {
            "filename": filename,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "media_type": "image/png",
            "generated_at": result.generated_at,
        }
    rows = [{
        "roster_id": team.roster_id, "team": team.team_name,
        "rank": team.rank, "previous_rank": team.previous_rank,
        "movement": team.movement if team.previous_rank is not None else None,
        "score": team.score,
        "components": {
            "market_percentile": team.market_percentile,
            "ros_scoring_percentile": team.lineup_percentile,
            "season_results_percentile": team.season_percentile,
            "defense_percentile": team.defense_percentile,
            "market_points": team.market_points,
            "ros_scoring_points": team.lineup_points,
            "season_results_points": team.season_points,
            "defense_points": team.defense_points,
            "record_guardrail_applied": team.record_guardrail_applied,
            "weights": {"market": result.market_weight, "ros_scoring": result.lineup_weight,
                        "defense": result.defense_weight, "season_results": result.season_weight},
        },
    } for team in result.teams]
    payload = {
        "schema_version": 3,
        "publication_key": publication_key,
        "source_metadata": {
            "producer": "OTHER_LEAGUE_POWER_RANKS", "league_key": config.key,
            "league_id": result.league.league_id, "season": result.league.season,
            "ranking_week": result.league.week,
            "results_through_week": max(0, int(result.league.week) - 1),
            "generated_at": result.generated_at,
            "model_version": "cross-league-record-v2",
            "dynasty_sources": result.dynasty_sources,
            "lineup_sources": result.lineup_sources,
        },
        "official_power_rankings": rows,
        "playoff_odds": [{
            "roster_id": t.roster_id, "team": t.team_name,
            "projected_record": t.projected_record,
            "playoff": t.make_playoffs_pct, "division": t.win_division_pct,
            "bye": t.first_round_bye_pct, "final": t.make_final_pct,
            "championship": t.win_championship_pct,
        } for t in result.teams],
        "publication_assets": manifest,
        "notes": ["Authoritative power ranking from OTHER_LEAGUE_POWER_RANKS.",
                  "Division ranks must be calculated by filtering this overall order.",
                  "Scores include disclosed undefeated-record adjustments where applicable."],
    }
    dest = output_root / f"{config.key}.json"
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return dest
