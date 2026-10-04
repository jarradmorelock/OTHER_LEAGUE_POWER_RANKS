"""Projection-based rest-of-season offensive lineup ratings."""

from __future__ import annotations

import re
from statistics import mean
from typing import Any

from .engine import optimal_lineup_value
from .http import DataSourceError
from .models import LeagueSnapshot, PlayerIdentity


SLEEPER_BASE = "https://api.sleeper.app/v1"
OFFENSE = {"QB", "RB", "WR", "TE"}
YARDAGE_BONUS = re.compile(r"^bonus_(pass|rush|rec)_yd_(\d+)$")
COMBINED_YARDAGE_BONUS = re.compile(r"^bonus_rush_rec_yd_(\d+)$")


def ros_projection_weeks(snapshot: LeagueSnapshot) -> list[int]:
    """Return the remaining fantasy-relevant NFL weeks for ROS scoring."""
    start = max(snapshot.start_week, snapshot.week or snapshot.start_week)
    end = max(start, min(17, snapshot.playoff_week_start + 2))
    return list(range(start, end + 1))


def fetch_ros_team_values(
    client: Any,
    snapshot: LeagueSnapshot,
    players: dict[str, PlayerIdentity],
) -> tuple[dict[int, float], list[int], list[str]]:
    """Average each roster's best legal projected lineup across remaining weeks."""
    warnings: list[str] = []
    successful_weeks: list[int] = []
    team_week_totals: dict[int, list[float]] = {
        team.roster_id: [] for team in snapshot.teams
    }
    slots = [
        slot
        for slot in snapshot.roster_positions
        if slot in {"QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"}
    ]

    for week in ros_projection_weeks(snapshot):
        url = f"{SLEEPER_BASE}/projections/nfl/regular/{snapshot.season}/{week}"
        try:
            payload = client.get_json(url)
        except DataSourceError as exc:
            warnings.append(f"Sleeper Week {week} projections unavailable: {exc}")
            continue
        projections = _normalize_projection_payload(payload)
        if not projections:
            warnings.append(f"Sleeper Week {week} projections were empty; week omitted from ROS average.")
            continue

        projected_values: dict[str, float] = {}
        for player_id, row in projections.items():
            identity = players.get(player_id)
            if identity is None or identity.position not in OFFENSE:
                continue
            value = projection_fantasy_points(
                row,
                snapshot.scoring_settings,
                position=identity.position,
            )
            if value > 0:
                projected_values[player_id] = value

        if not projected_values:
            warnings.append(f"Sleeper Week {week} had no mapped offensive projections; week omitted from ROS average.")
            continue

        successful_weeks.append(week)
        for team in snapshot.teams:
            total = optimal_lineup_value(
                team.player_ids,
                slots,
                players,
                projected_values,
                one_qb=not snapshot.is_superflex,
            )
            team_week_totals[team.roster_id].append(total)

    if not successful_weeks:
        return {}, [], warnings

    values = {
        roster_id: mean(weekly_totals)
        for roster_id, weekly_totals in team_week_totals.items()
        if weekly_totals
    }
    if set(values) != {team.roster_id for team in snapshot.teams} or any(
        value <= 0 for value in values.values()
    ):
        warnings.append(
            "ROS projection coverage was insufficient for at least one roster; "
            "the ranking engine will use its legacy starter-ranking fallback."
        )
        return {}, successful_weeks, warnings
    return values, successful_weeks, warnings


def projection_fantasy_points(
    projection: dict[str, Any],
    scoring_settings: dict[str, float],
    *,
    position: str = "",
) -> float:
    """Score raw Sleeper projection stats with the league's offensive settings."""
    if not isinstance(projection, dict):
        return 0.0
    stats = projection.get("stats")
    if not isinstance(stats, dict):
        stats = projection

    score = 0.0
    matched = False
    settings = scoring_settings or {}

    for key, weight in settings.items():
        if str(key).startswith("bonus_") or key not in stats:
            continue
        try:
            score += float(stats.get(key) or 0.0) * float(weight or 0.0)
            matched = True
        except (TypeError, ValueError):
            continue

    rec = _number(stats.get("rec"))
    position_key = str(position or "").lower()
    position_bonus_key = f"bonus_rec_{position_key}"
    if rec and position_bonus_key in settings:
        score += rec * _number(settings.get(position_bonus_key))
        matched = True

    for key, raw_bonus in settings.items():
        bonus = _number(raw_bonus)
        if not bonus:
            continue
        match = YARDAGE_BONUS.fullmatch(str(key))
        if match:
            stat_key = f"{match.group(1)}_yd"
            if _number(stats.get(stat_key)) >= int(match.group(2)):
                score += bonus
                matched = True
            continue
        match = COMBINED_YARDAGE_BONUS.fullmatch(str(key))
        if match:
            combined = _number(stats.get("rush_yd")) + _number(stats.get("rec_yd"))
            if combined >= int(match.group(1)):
                score += bonus
                matched = True

    if matched:
        return round(score, 3)

    for container in (projection, stats):
        for key in ("pts", "points", "fantasy_points"):
            try:
                return round(float(container.get(key)), 3)
            except (TypeError, ValueError, AttributeError):
                continue
    return 0.0


def _normalize_projection_payload(payload: Any) -> dict[str, dict[str, Any]]:
    if isinstance(payload, dict):
        return {
            str(player_id): row
            for player_id, row in payload.items()
            if isinstance(row, dict)
        }
    if isinstance(payload, list):
        output: dict[str, dict[str, Any]] = {}
        for row in payload:
            if not isinstance(row, dict):
                continue
            player_id = row.get("player_id") or row.get("player_id_string")
            if player_id is not None:
                output[str(player_id)] = row
        return output
    return {}


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
