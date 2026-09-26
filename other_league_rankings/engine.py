"""Shared power-rank calculation for keeper, dynasty, 1QB, and Superflex leagues."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from datetime import datetime, timezone

from .models import LeagueSnapshot, LeagueTeam, MarketBundle, PlayerIdentity, RankedTeam, RankingResult, ValueBook


RECORD_SHARE_OF_SEASON = 0.80
POINTS_SHARE_OF_SEASON = 0.20
GUARDRAIL_MIN_GAMES = 8
GUARDRAIL_WIN_GAP = 4.0
GUARDRAIL_MAX_SCORE_LEAD = 10.0
OFFENSE = {"QB", "RB", "WR", "TE"}
ELIGIBLE = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "FLEX": {"RB", "WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
}
IDP_ELIGIBLE = {
    "DL": {"DL", "DE", "DT", "NT", "EDGE"},
    "LB": {"LB", "ILB", "OLB"},
    "DB": {"DB", "CB", "S", "FS", "SS"},
}
IDP_ELIGIBLE["IDP_FLEX"] = set().union(*IDP_ELIGIBLE.values())


@dataclass
class _TeamScore:
    team: LeagueTeam
    market: float
    lineup: float
    defense: float
    season: float
    market_points: float
    lineup_points: float
    defense_points: float
    season_points: float
    score: float
    record_guardrail_applied: bool = False


def ranking_weights(completed_games: int) -> tuple[float, float, float]:
    if completed_games <= 0:
        return (0.45, 0.55, 0.0)
    if completed_games <= 3:
        return (0.35, 0.45, 0.20)
    if completed_games <= 7:
        return (0.30, 0.40, 0.30)
    return (0.25, 0.35, 0.40)


def sec_ranking_weights(completed_games: int) -> tuple[float, float, float, float]:
    """Return SEC-only market, offense, results, and raw IDP projection weights."""
    if completed_games <= 0:
        return (0.45, 0.55, 0.0, 0.0)
    if completed_games <= 3:
        return (0.30, 0.35, 0.20, 0.15)
    if completed_games <= 7:
        return (0.25, 0.32, 0.30, 0.13)
    return (0.20, 0.30, 0.40, 0.10)


def rank_league(
    snapshot: LeagueSnapshot,
    bundle: MarketBundle,
    previous_ranks: dict[str, int] | None = None,
    generated_at: str = "",
) -> RankingResult:
    previous_ranks = previous_ranks or {}
    dynasty_books = [book for book in bundle.dynasty_books if book.player_values or book.pick_values]
    lineup_books = [book for book in bundle.lineup_books if book.player_values]
    if not dynasty_books or not lineup_books:
        raise ValueError("At least one dynasty and one lineup source are required")
    if not 0.0 <= snapshot.defense_weight < 1.0:
        raise ValueError("Defense weight must be between 0 inclusive and 1 exclusive")

    roster_ids = [team.roster_id for team in snapshot.teams]
    completed_games = max((team.games for team in snapshot.teams), default=0)
    source_totals: dict[str, dict[int, float]] = {}
    source_percentiles: dict[str, dict[int, float]] = {}
    coverage_warnings: list[str] = []
    for book in dynasty_books:
        if not _has_roster_coverage(snapshot, book, bundle.players, minimum=0.55):
            coverage_warnings.append(f"Market source {book.name} excluded: at least 55% roster coverage is required for every team.")
            continue
        totals = {
            team.roster_id: sum(
                book.player_values.get(pid, 0.0)
                for pid in team.player_ids
                if not snapshot.idp_partial or (pid in bundle.players and bundle.players[pid].position in OFFENSE)
            )
            + sum(_pick_value(book, pick.year, pick.round) for pick in team.picks)
            for team in snapshot.teams
        }
        if max(totals.values(), default=0) > 0:
            source_totals[book.name] = totals
            source_percentiles[book.name] = percentile_scores(totals)

    starter_slots = [
        "QB" if slot == "SUPER_FLEX" and not snapshot.is_superflex else slot
        for slot in snapshot.roster_positions
        if slot in ELIGIBLE
    ]
    if snapshot.idp_partial:
        starter_slots = [slot for slot in starter_slots if slot in ELIGIBLE]
    for book in lineup_books:
        if not _has_roster_coverage(snapshot, book, bundle.players, minimum=0.35):
            coverage_warnings.append(f"Starter source {book.name} excluded: at least 35% roster coverage is required for every team.")
            continue
        totals = {
            team.roster_id: optimal_lineup_value(
                team.player_ids, starter_slots, bundle.players, book.player_values,
                one_qb=not snapshot.is_superflex,
            )
            for team in snapshot.teams
        }
        if max(totals.values(), default=0) > 0:
            source_totals[book.name] = totals
            source_percentiles[book.name] = percentile_scores(totals)

    defense_sources: list[str] = []
    defense_percentiles: dict[int, float] = {rid: 0.0 for rid in roster_ids}
    idp_slots = [slot for slot in snapshot.roster_positions if slot in IDP_ELIGIBLE]
    for book in bundle.defense_books:
        if not (book.scoring_adjusted or book.raw_projection):
            coverage_warnings.append(
                f"Defense source {book.name} excluded: it is neither adjusted to league scoring nor a raw provider projection."
            )
            continue
        if not idp_slots or not _has_defense_coverage(snapshot, book, bundle.players, minimum=0.35):
            coverage_warnings.append(
                f"Defense source {book.name} excluded: legal IDP slots and at least 35% mapped roster coverage are required for every team."
            )
            continue
        totals = {
            team.roster_id: optimal_idp_lineup_value(
                team.player_ids, idp_slots, bundle.players, book.player_values
            )
            for team in snapshot.teams
        }
        if max(totals.values(), default=0) > 0:
            source_totals[book.name] = totals
            source_percentiles[book.name] = percentile_scores(totals)
            defense_sources.append(book.name)
    scheduled_defense_weight = (
        sec_ranking_weights(completed_games)[3]
        if snapshot.idp_partial and snapshot.defense_weight > 0
        else 0.0
    )
    if scheduled_defense_weight > 0 and not defense_sources:
        raise ValueError("Defense weight is enabled but no defense source has sufficient IDP coverage")
    if defense_sources:
        defense_percentiles = {
            rid: mean(source_percentiles[name][rid] for name in defense_sources)
            for rid in roster_ids
        }

    usable_dynasty = [book.name for book in dynasty_books if book.name in source_percentiles]
    usable_lineup = [book.name for book in lineup_books if book.name in source_percentiles]
    if not usable_dynasty or not usable_lineup:
        raise ValueError("Available sources did not map enough roster values for every team")
    market_pct = {rid: mean(source_percentiles[name][rid] for name in usable_dynasty) for rid in roster_ids}
    lineup_pct = {rid: mean(source_percentiles[name][rid] for name in usable_lineup) for rid in roster_ids}
    starter_ratings = {
        rid: source_totals[usable_lineup[0]][rid] if len(usable_lineup) == 1 else lineup_pct[rid]
        for rid in roster_ids
    }

    has_results = completed_games > 0
    season_pct: dict[int, float] = {}
    if has_results:
        record_pct = percentile_scores({team.roster_id: team.win_percentage for team in snapshot.teams})
        points_pct = percentile_scores({team.roster_id: team.points_for for team in snapshot.teams})
        season_pct = {
            rid: record_pct[rid] * RECORD_SHARE_OF_SEASON + points_pct[rid] * POINTS_SHARE_OF_SEASON
            for rid in roster_ids
        }
    if snapshot.idp_partial and snapshot.defense_weight > 0:
        market_weight, lineup_weight, season_weight, scheduled_defense_weight = sec_ranking_weights(completed_games)
        defense_weight = scheduled_defense_weight if defense_sources else 0.0
    else:
        market_weight, lineup_weight, season_weight = ranking_weights(completed_games)
        defense_weight = 0.0
    scored: list[_TeamScore] = []
    for team in snapshot.teams:
        rid = team.roster_id
        market_points = market_pct[rid] * market_weight
        lineup_points = lineup_pct[rid] * lineup_weight
        defense_points = defense_percentiles[rid] * defense_weight
        season_points = season_pct.get(rid, 0.0) * season_weight
        scored.append(_TeamScore(
            team, market_pct[rid], lineup_pct[rid], defense_percentiles[rid], season_pct.get(rid, 0.0),
            market_points, lineup_points, defense_points, season_points,
            market_points + lineup_points + defense_points + season_points,
        ))

    guardrail_active = completed_games >= GUARDRAIL_MIN_GAMES
    if guardrail_active:
        _apply_record_guardrail(scored)
    scored.sort(key=lambda item: (item.score, item.market, item.lineup, item.team.points_for), reverse=True)
    ranks = {item.team.roster_id: rank for rank, item in enumerate(scored, start=1)}
    source_ranks = {name: ordinal_ranks(totals) for name, totals in source_totals.items()}
    ranked: list[RankedTeam] = []
    for rank, item in enumerate(scored, start=1):
        team = item.team
        prior = previous_ranks.get(str(team.roster_id))
        ranked.append(RankedTeam(
            rank=rank,
            roster_id=team.roster_id,
            team_name=team.team_name,
            owner_name=team.owner_name,
            record=team.record,
            points_for=team.points_for,
            score=round(item.score, 1),
            market_percentile=round(item.market, 1),
            lineup_percentile=round(item.lineup, 1),
            season_percentile=round(season_pct[team.roster_id], 1) if has_results else None,
            market_points=round(item.market_points, 2),
            lineup_points=round(item.lineup_points, 2),
            season_points=round(item.season_points, 2),
            starter_rating=round(starter_ratings[team.roster_id], 2),
            defense_percentile=round(item.defense, 1),
            defense_points=round(item.defense_points, 2),
            previous_rank=prior,
            movement=(prior - rank) if prior is not None else 0,
            record_guardrail_applied=item.record_guardrail_applied,
            source_ranks={name: values[team.roster_id] for name, values in source_ranks.items()},
        ))
    return RankingResult(
        league=snapshot,
        teams=ranked,
        dynasty_sources=usable_dynasty,
        lineup_sources=usable_lineup,
        has_season_results=has_results,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        market_weight=market_weight,
        lineup_weight=lineup_weight,
        season_weight=season_weight,
        record_guardrail_active=guardrail_active,
        warnings=[*snapshot.warnings, *bundle.warnings, *coverage_warnings],
        defense_weight=defense_weight,
        defense_sources=defense_sources,
    )


def _apply_record_guardrail(scored: list[_TeamScore]) -> None:
    by_record = sorted(scored, key=lambda item: (item.team.wins + item.team.ties * 0.5, item.team.win_percentage), reverse=True)
    for item in by_record:
        if item.team.games < GUARDRAIL_MIN_GAMES:
            continue
        record_wins = item.team.wins + item.team.ties * 0.5
        better = [other for other in by_record if other.team.games >= GUARDRAIL_MIN_GAMES and (other.team.wins + other.team.ties * 0.5) - record_wins >= GUARDRAIL_WIN_GAP]
        if not better:
            continue
        ceiling = min(other.score + GUARDRAIL_MAX_SCORE_LEAD for other in better)
        if item.score <= ceiling:
            continue
        roster_points = item.market_points + item.lineup_points + item.defense_points
        target = max(0.0, ceiling - item.season_points)
        scale = min(1.0, target / roster_points) if roster_points else 0.0
        item.market_points *= scale
        item.lineup_points *= scale
        item.defense_points *= scale
        item.score = item.market_points + item.lineup_points + item.defense_points + item.season_points
        item.record_guardrail_applied = True


def percentile_scores(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return {}
    if len(set(values.values())) == 1:
        return {key: 50.0 for key in values}
    ordered = sorted(values.items(), key=lambda pair: pair[1])
    result: dict[int, float] = {}
    denominator = max(1, len(ordered) - 1)
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        score = ((index + end) / 2) / denominator * 100
        for cursor in range(index, end + 1):
            result[ordered[cursor][0]] = score
        index = end + 1
    return result


def ordinal_ranks(values: dict[int, float]) -> dict[int, int]:
    return {rid: rank for rank, (rid, _) in enumerate(sorted(values.items(), key=lambda pair: (-pair[1], pair[0])), start=1)}


def optimal_lineup_value(
    player_ids: list[str],
    slots: list[str],
    players: dict[str, PlayerIdentity],
    values: dict[str, float],
    *,
    one_qb: bool = False,
) -> float:
    legal_slots = ["QB" if slot == "SUPER_FLEX" and one_qb else slot for slot in slots if slot in ELIGIBLE]
    candidates = [
        (pid, players[pid].position, max(0.0, values.get(pid, 0.0)))
        for pid in player_ids
        if pid in players and players[pid].position in OFFENSE
    ]
    if not legal_slots:
        return 0.0
    # Exact maximum-weight bipartite matching, with one dummy option per slot
    # so missing legal starters contribute zero. The Hungarian algorithm is
    # polynomial in roster/slot size, unlike subset search over every roster
    # player (which became unusable on full Sleeper rosters).
    dummy_count = len(legal_slots)
    forbidden_cost = 1e12
    costs = []
    for slot in legal_slots:
        eligible = ELIGIBLE[slot]
        costs.append([
            -value if position in eligible else forbidden_cost
            for _pid, position, value in candidates
        ] + [0.0] * dummy_count)
    assignment = _minimum_cost_assignment(costs)
    total = 0.0
    for slot_index, candidate_index in enumerate(assignment):
        if candidate_index < len(candidates):
            _pid, position, value = candidates[candidate_index]
            if position in ELIGIBLE[legal_slots[slot_index]]:
                total += value
    return total


def optimal_idp_lineup_value(
    player_ids: list[str],
    slots: list[str],
    players: dict[str, PlayerIdentity],
    values: dict[str, float],
) -> float:
    """Maximize projected IDP value under DL/LB/DB and IDP_FLEX eligibility."""
    legal_slots = [slot for slot in slots if slot in IDP_ELIGIBLE]
    candidates = [
        (pid, players[pid].position, max(0.0, values.get(pid, 0.0)))
        for pid in player_ids
        if pid in players and any(players[pid].position in positions for positions in IDP_ELIGIBLE.values())
    ]
    if not legal_slots:
        return 0.0
    dummy_count = len(legal_slots)
    forbidden_cost = 1e12
    costs = [
        [
            -value if position in IDP_ELIGIBLE[slot] else forbidden_cost
            for _pid, position, value in candidates
        ] + [0.0] * dummy_count
        for slot in legal_slots
    ]
    assignment = _minimum_cost_assignment(costs)
    return sum(
        candidates[candidate_index][2]
        for slot_index, candidate_index in enumerate(assignment)
        if candidate_index < len(candidates)
        and candidates[candidate_index][1] in IDP_ELIGIBLE[legal_slots[slot_index]]
    )


def _minimum_cost_assignment(costs: list[list[float]]) -> list[int]:
    """Rectangular Hungarian assignment; rows <= columns are guaranteed."""
    row_count = len(costs)
    if row_count == 0:
        return []
    column_count = len(costs[0])
    if row_count > column_count:
        raise ValueError("Assignment requires at least as many columns as rows")
    u = [0.0] * (row_count + 1)
    v = [0.0] * (column_count + 1)
    p = [0] * (column_count + 1)
    way = [0] * (column_count + 1)
    for row in range(1, row_count + 1):
        p[0] = row
        column0 = 0
        min_value = [float("inf")] * (column_count + 1)
        used = [False] * (column_count + 1)
        while True:
            used[column0] = True
            row0 = p[column0]
            delta = float("inf")
            column1 = 0
            for column in range(1, column_count + 1):
                if used[column]:
                    continue
                current = costs[row0 - 1][column - 1] - u[row0] - v[column]
                if current < min_value[column]:
                    min_value[column] = current
                    way[column] = column0
                if min_value[column] < delta:
                    delta = min_value[column]
                    column1 = column
            for column in range(column_count + 1):
                if used[column]:
                    u[p[column]] += delta
                    v[column] -= delta
                else:
                    min_value[column] -= delta
            column0 = column1
            if p[column0] == 0:
                break
        while True:
            column1 = way[column0]
            p[column0] = p[column1]
            column0 = column1
            if column0 == 0:
                break
    assignment = [-1] * row_count
    for column in range(1, column_count + 1):
        if p[column]:
            assignment[p[column] - 1] = column - 1
    return assignment


def _has_roster_coverage(
    snapshot: LeagueSnapshot,
    book: ValueBook,
    players: dict[str, PlayerIdentity],
    *,
    minimum: float,
) -> bool:
    for team in snapshot.teams:
        rostered = [
            pid for pid in team.player_ids
            if pid in players and (not snapshot.idp_partial or players[pid].position in OFFENSE)
        ]
        if not rostered:
            return False
        mapped = sum(1 for pid in rostered if book.player_values.get(pid, 0.0) > 0)
        if mapped / len(rostered) < minimum:
            return False
    return bool(snapshot.teams)


def _has_defense_coverage(
    snapshot: LeagueSnapshot,
    book: ValueBook,
    players: dict[str, PlayerIdentity],
    *,
    minimum: float,
) -> bool:
    idp_positions = set().union(*IDP_ELIGIBLE.values())
    for team in snapshot.teams:
        rostered = [
            pid for pid in team.player_ids
            if pid in players and players[pid].position in idp_positions
        ]
        if not rostered:
            return False
        mapped = sum(1 for pid in rostered if pid in book.player_values)
        if mapped / len(rostered) < minimum:
            return False
    return bool(snapshot.teams)


def _pick_value(book: ValueBook, year: int, round_number: int) -> float:
    direct = book.pick_values.get((year, "mid", round_number))
    if direct is not None:
        return direct
    same_round = [(pick_year, value) for (pick_year, tier, pick_round), value in book.pick_values.items() if tier == "mid" and pick_round == round_number]
    if not same_round:
        return 0.0
    closest_year, value = min(same_round, key=lambda pair: abs(pair[0] - year))
    return value * (0.80 ** max(0, year - closest_year))
