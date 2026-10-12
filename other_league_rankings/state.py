"""Atomic, isolated publication history for each league."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import tempfile

from .models import RankingResult


@dataclass
class LeagueState:
    rank_by_roster_id: dict[str, int] = field(default_factory=dict)
    last_post_key: str | None = None


class StateStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, league_key: str) -> Path:
        if not isinstance(league_key, str) or not re.fullmatch(r"[a-z0-9_-]+", league_key):
            raise ValueError("Invalid league key for publication state")
        return self.root / f"{league_key}.json"

    def load(self, league_key: str) -> LeagueState:
        path = self.path_for(league_key)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return LeagueState()
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Unable to read state for league {league_key}: {exc}") from exc
        ranks = raw.get("rank_by_roster_id") if isinstance(raw, dict) else None
        post_key = raw.get("last_post_key") if isinstance(raw, dict) else None
        if not isinstance(ranks, dict) or (post_key is not None and not isinstance(post_key, str)):
            raise ValueError(f"Malformed saved state for league {league_key}")
        clean_ranks: dict[str, int] = {}
        for roster_id, rank in ranks.items():
            if not isinstance(roster_id, str) or not isinstance(rank, int) or rank < 1:
                raise ValueError(f"Malformed rank history for league {league_key}")
            clean_ranks[roster_id] = rank
        return LeagueState(clean_ranks, post_key)

    def _save_snapshot(self, league_key: str, result: RankingResult, post_key: str | None, publication: str) -> None:
        path = self.path_for(league_key)
        existing = self.load(league_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        old_generated_at = None
        if path.exists():
            old_generated_at = json.loads(path.read_text(encoding="utf-8")).get("generated_at")
        if old_generated_at:
            try:
                prior = datetime.fromisoformat(str(old_generated_at).replace("Z", "+00:00"))
                current = datetime.fromisoformat(result.generated_at.replace("Z", "+00:00"))
                if prior.tzinfo is not None and current.tzinfo is not None and current < prior:
                    raise ValueError("Refusing stale ranking publication: older than saved baseline")
            except ValueError as exc:
                if "Refusing stale" in str(exc):
                    raise
        ranks = {str(team.roster_id): int(team.rank) for team in result.teams}
        payload = {
            "last_post_key": post_key if post_key is not None else existing.last_post_key,
            "generated_at": result.generated_at,
            "rank_by_roster_id": ranks,
        }
        stamp = datetime.fromisoformat(result.generated_at.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        history_file = path.parent / "history" / league_key / f"{stamp}-{publication}.json"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history = {
            "schema_version": 1,
            "publication": publication,
            "generated_at": result.generated_at,
            "league_id": str(result.league.league_id),
            "season": result.league.season,
            "ranking_week": result.league.week,
            "post_key": payload["last_post_key"],
            "previous_rank_by_roster_id": existing.rank_by_roster_id,
            "rank_by_roster_id": ranks,
            "teams": [
                {"roster_id": int(team.roster_id), "team": team.team_name, "rank": int(team.rank),
                 "previous_rank": existing.rank_by_roster_id.get(str(team.roster_id)),
                 "movement": (existing.rank_by_roster_id[str(team.roster_id)] - int(team.rank)
                              if str(team.roster_id) in existing.rank_by_roster_id else None),
                 "score": team.score}
                for team in result.teams
            ],
        }
        encoded = json.dumps(history, sort_keys=True, indent=2) + "\n"
        if history_file.exists():
            if history_file.read_text(encoding="utf-8") != encoded:
                raise ValueError("Ranking history snapshot collision")
        else:
            history_file.write_text(encoded, encoding="utf-8")
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{league_key}.", suffix=".tmp", delete=False) as handle:
                temporary_path = Path(handle.name)
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def save_success(self, league_key: str, result: RankingResult, post_key: str) -> None:
        if not post_key:
            raise ValueError("A post key is required before saving publication state")
        self._save_snapshot(league_key, result, post_key, "discord")

    def save_rank_history_only(self, league_key: str, result: RankingResult) -> None:
        """Advance Tuesday movement baseline while preserving the Saturday duplicate-post key."""
        self._save_snapshot(league_key, result, None, "editorial")

