"""Read and normalize a league's current Sleeper settings and results."""

from __future__ import annotations

from typing import Any

from .http import DataSourceError
from .models import DraftPick, LeagueConfig, LeagueMatchup, LeagueSnapshot, LeagueTeam


SLEEPER_BASE = "https://api.sleeper.app/v1"


def fetch_snapshot(client: Any, config: LeagueConfig, week: int | None = None) -> LeagueSnapshot:
    """Fetch current Sleeper state. Network access is injected for easy testing."""
    league_id = config.league_id
    league = client.get_json(f"{SLEEPER_BASE}/league/{league_id}")
    users = client.get_json(f"{SLEEPER_BASE}/league/{league_id}/users")
    rosters = client.get_json(f"{SLEEPER_BASE}/league/{league_id}/rosters")
    traded_picks = client.get_json(f"{SLEEPER_BASE}/league/{league_id}/traded_picks")
    state = client.get_json(f"{SLEEPER_BASE}/state/nfl")
    if not isinstance(league, dict):
        raise DataSourceError(f"Sleeper returned invalid league settings for {config.key}")
    settings = league.get("settings") or {}
    start_week = _int(settings.get("start_week"), 1)
    playoff_week_start = _int(settings.get("playoff_week_start"), 15)
    current_week = week if week is not None else _int(state.get("week"), _int(settings.get("leg"), 0))
    # Fetch the regular-season schedule window: past weeks feed the form
    # adjustment, and current/future weeks drive the playoff simulation.
    end_week = max(start_week - 1, playoff_week_start - 1)
    matchups: list[LeagueMatchup] = []
    for matchup_week in range(start_week, end_week + 1):
        rows = client.get_json(f"{SLEEPER_BASE}/league/{league_id}/matchups/{matchup_week}")
        if isinstance(rows, list):
            matchups.extend(_normalize_matchups(rows, matchup_week))
    try:
        bracket = client.get_json(f"{SLEEPER_BASE}/league/{league_id}/winners_bracket")
        if not isinstance(bracket, list):
            bracket = []
    except DataSourceError:
        bracket = []
    return normalize_snapshot_payloads(
        config, league, users, rosters, traded_picks, state, matchups, bracket,
        current_week=current_week,
    )


def normalize_snapshot_payloads(
    config: LeagueConfig,
    league: dict[str, Any],
    users: list[dict[str, Any]],
    rosters: list[dict[str, Any]],
    traded_picks: list[dict[str, Any]],
    state: dict[str, Any],
    matchups: list[LeagueMatchup] | list[dict[str, Any]],
    playoff_bracket: list[dict[str, Any]],
    *,
    current_week: int | None = None,
) -> LeagueSnapshot:
    """Pure normalization boundary for Sleeper API payloads."""
    if not isinstance(league, dict) or not isinstance(league.get("settings"), dict):
        raise ValueError("Sleeper league settings are missing or malformed")
    if not isinstance(rosters, list) or len(rosters) < 2:
        raise ValueError("Sleeper rosters are missing or fewer than two teams were returned")
    if not isinstance(users, list):
        raise ValueError("Sleeper users are missing or malformed")
    if not isinstance(state, dict):
        raise ValueError("Sleeper NFL state is missing or malformed")
    roster_positions = [str(slot) for slot in league.get("roster_positions") or []]
    if not roster_positions:
        raise ValueError("Sleeper roster positions are missing")
    settings = league["settings"]
    scoring = league.get("scoring_settings") or {}
    if not isinstance(scoring, dict):
        raise ValueError("Sleeper scoring settings are malformed")
    scoring_settings: dict[str, float] = {}
    warnings: list[str] = []
    for key, raw_value in scoring.items():
        try:
            scoring_settings[str(key)] = float(raw_value)
        except (TypeError, ValueError):
            warnings.append(f"Scoring setting {key!r} is nonnumeric and was omitted from numeric scoring inputs.")
    expected_bonus = config.expected_bonus_rec_te
    if expected_bonus is not None:
        observed_bonus = scoring_settings.get("bonus_rec_te", 0.0)
        if abs(observed_bonus - expected_bonus) > 1e-9:
            warnings.append(
                f"Sleeper bonus_rec_te is {observed_bonus:g}; configured expectation is {expected_bonus:g}."
            )
    supported_slots = {"QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"}
    non_starting_slots = {"BN", "IR", "TAXI", "PUP", "RES"}
    unexpected_slots = sorted({slot for slot in roster_positions if slot not in supported_slots and slot not in non_starting_slots})
    if unexpected_slots and config.mode != "offense_only_partial":
        warnings.append(f"Unsupported lineup slots require review and are omitted from starter value: {', '.join(unexpected_slots)}.")
    if not any(slot in {"QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"} for slot in roster_positions):
        warnings.append("Sleeper roster has no recognized offensive starting slots.")

    user_map = {
        str(user.get("user_id")): user
        for user in users
        if isinstance(user, dict) and user.get("user_id") is not None
    }
    team_list: list[LeagueTeam] = []
    roster_ids: set[int] = set()
    for roster in rosters:
        if not isinstance(roster, dict) or roster.get("roster_id") is None:
            raise ValueError("Sleeper returned a roster without roster_id")
        roster_id = int(roster["roster_id"])
        roster_ids.add(roster_id)
        owner_id = str(roster.get("owner_id") or "")
        user = user_map.get(owner_id, {})
        user_meta = user.get("metadata") or {}
        roster_meta = roster.get("metadata") or {}
        owner_name = str(user.get("display_name") or user.get("username") or f"Roster {roster_id}")
        team_name = str(roster_meta.get("team_name") or user_meta.get("team_name") or owner_name).strip()
        roster_settings = roster.get("settings") or {}
        points = _float(roster_settings.get("fpts"), 0.0) + _float(roster_settings.get("fpts_decimal"), 0.0) / 100
        team_list.append(LeagueTeam(
            roster_id=roster_id,
            owner_id=owner_id,
            team_name=team_name,
            owner_name=owner_name,
            player_ids=[str(player_id) for player_id in roster.get("players") or []],
            picks=[],
            wins=_int(roster_settings.get("wins"), 0),
            losses=_int(roster_settings.get("losses"), 0),
            ties=_int(roster_settings.get("ties"), 0),
            points_for=points,
            division=_int(roster_settings.get("division"), 0),
        ))
    draft_rounds = _int(settings.get("draft_rounds"), 4)
    season = _int(league.get("season"), _int(state.get("season"), 0))
    if season == 0:
        raise ValueError("Sleeper did not provide a valid season")
    in_season = str(league.get("status") or "") in {"in_season", "post_season"}
    pick_start = season + 1 if in_season else season
    ownership = {
        (year, round_number, original): original
        for year in range(pick_start, pick_start + 3)
        for round_number in range(1, draft_rounds + 1)
        for original in roster_ids
    }
    for pick in traded_picks if isinstance(traded_picks, list) else []:
        try:
            key = (int(pick["season"]), int(pick["round"]), int(pick["roster_id"]))
            owner = int(pick.get("owner_id") or pick["roster_id"])
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if key in ownership and owner in roster_ids:
            ownership[key] = owner
    team_by_id = {team.roster_id: team for team in team_list}
    for (year, round_number, original), owner in ownership.items():
        team_by_id[owner].picks.append(DraftPick(year, round_number, original))
    for team in team_list:
        team.picks.sort(key=lambda pick: (pick.year, pick.round, pick.original_roster_id))

    normalized_matchups = [
        row if isinstance(row, LeagueMatchup) else _matchup_from_row(row)
        for row in matchups if isinstance(row, (LeagueMatchup, dict))
    ]
    detected_superflex = "SUPER_FLEX" in roster_positions or roster_positions.count("QB") > 1
    is_superflex = False if config.quarterback_mode == "one_qb" else detected_superflex
    week = current_week if current_week is not None else _int(state.get("week"), _int(settings.get("leg"), 0))
    return LeagueSnapshot(
        league_id=config.league_id,
        league_name=str(league.get("name") or config.name),
        season=season,
        week=week,
        is_superflex=is_superflex,
        ppr=scoring_settings.get("rec", 0.0),
        roster_positions=roster_positions,
        teams=team_list,
        scoring_settings=scoring_settings,
        start_week=_int(settings.get("start_week"), 1),
        playoff_week_start=_int(settings.get("playoff_week_start"), 15),
        playoff_teams=_int(settings.get("playoff_teams"), max(2, len(team_list) // 2)),
        divisions=max(1, _int(settings.get("divisions"), 1)),
        playoff_round_type=_int(settings.get("playoff_round_type"), 0),
        league_average_match=_int(settings.get("league_average_match"), 0) == 1,
        matchups=normalized_matchups,
        playoff_bracket=playoff_bracket if isinstance(playoff_bracket, list) else [],
        idp_partial=config.mode == "offense_only_partial",
        warnings=warnings,
        defense_weight=config.defense_weight,
    )


def _normalize_matchups(rows: list[dict[str, Any]], week: int) -> list[LeagueMatchup]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("matchup_id") is not None:
            grouped.setdefault(int(row["matchup_id"]), []).append(row)
    result: list[LeagueMatchup] = []
    for matchup_id, pair in grouped.items():
        if len(pair) != 2:
            continue
        pair.sort(key=lambda row: int(row.get("roster_id") or 0))
        first, second = pair
        result.append(LeagueMatchup(
            week=week,
            matchup_id=matchup_id,
            roster_one=int(first["roster_id"]),
            roster_two=int(second["roster_id"]),
            points_one=_float(first.get("custom_points", first.get("points")), 0.0),
            points_two=_float(second.get("custom_points", second.get("points")), 0.0),
        ))
    return result


def _matchup_from_row(row: dict[str, Any]) -> LeagueMatchup:
    return LeagueMatchup(
        week=_int(row.get("week"), 0),
        matchup_id=_int(row.get("matchup_id"), 0),
        roster_one=_int(row.get("roster_one"), 0),
        roster_two=_int(row.get("roster_two"), 0),
        points_one=_float(row.get("points_one"), 0.0),
        points_two=_float(row.get("points_two"), 0.0),
    )


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
