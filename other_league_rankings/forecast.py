"""Deterministic Monte Carlo playoff and championship estimates."""

from __future__ import annotations

from math import erf, floor, sqrt
import random
from statistics import mean, pstdev

from .models import LeagueSnapshot, RankingResult


DEFAULT_SIMULATIONS = 10_000


def attach_forecast(result: RankingResult, simulations: int = DEFAULT_SIMULATIONS) -> None:
    if simulations <= 0 or len(result.teams) < 2:
        raise ValueError("Forecast requires positive simulations and at least two teams")
    snapshot = result.league
    ratings = {team.roster_id: team.starter_rating for team in result.teams}
    probabilities = rating_probabilities(ratings)
    remaining = [m for m in snapshot.matchups if snapshot.week <= m.week < snapshot.playoff_week_start]
    projected = {team.roster_id: team.wins + team.ties * 0.5 for team in snapshot.teams}
    for matchup in remaining:
        chance = _game_probability(probabilities[matchup.roster_one], probabilities[matchup.roster_two])
        projected[matchup.roster_one] += chance
        projected[matchup.roster_two] += 1.0 - chance
    regular_season_games = max(0, snapshot.playoff_week_start - snapshot.start_week)
    projected_records = {}
    for team in snapshot.teams:
        wins = max(0, min(regular_season_games, int(floor(projected[team.roster_id] + 0.5))))
        projected_records[team.roster_id] = f"{wins}-{max(0, regular_season_games - wins)}"

    rng = random.Random(f"{snapshot.league_id}:{snapshot.season}:{snapshot.week}:{simulations}")
    counts = {team.roster_id: {key: 0 for key in ("playoffs", "division", "bye", "final", "champion")} for team in snapshot.teams}
    if snapshot.week >= snapshot.playoff_week_start and snapshot.playoff_bracket:
        _simulate_active(snapshot, probabilities, counts, simulations, rng)
    else:
        _simulate_season(snapshot, probabilities, remaining, counts, simulations, rng)
    for team in result.teams:
        values = counts[team.roster_id]
        team.projected_record = projected_records[team.roster_id]
        team.make_playoffs_pct = round(values["playoffs"] / simulations * 100, 1)
        team.win_division_pct = round(values["division"] / simulations * 100, 1)
        team.first_round_bye_pct = round(values["bye"] / simulations * 100, 1)
        team.make_final_pct = round(values["final"] / simulations * 100, 1)
        team.win_championship_pct = round(values["champion"] / simulations * 100, 1)
    result.forecast_simulations = simulations
    result.forecast_model = f"{result.lineup_sources[0] if result.lineup_sources else 'starter values'} + Sleeper schedule"


def rating_probabilities(ratings: dict[int, float]) -> dict[int, float]:
    values = list(ratings.values())
    if not values:
        return {}
    average, deviation = mean(values), pstdev(values)
    if deviation <= 1e-12:
        return {roster_id: 0.5 for roster_id in ratings}
    return {rid: 0.5 * (1 + erf(((rating - average) / deviation) / sqrt(2))) for rid, rating in ratings.items()}


def _game_probability(one: float, two: float) -> float:
    return max(0.05, min(0.95, 0.5 + (one - two) / 2))


def _simulate_season(snapshot: LeagueSnapshot, probabilities, remaining, counts, simulations, rng) -> None:
    ids = [team.roster_id for team in snapshot.teams]
    base_wins = {team.roster_id: team.wins + team.ties * 0.5 for team in snapshot.teams}
    divisions = {}
    if snapshot.divisions > 1:
        for team in snapshot.teams:
            if team.division > 0:
                divisions.setdefault(team.division, []).append(team.roster_id)
    playoff_count = min(len(ids), max(2, snapshot.playoff_teams))
    bracket_size = 1 << (playoff_count - 1).bit_length()
    bye_count = max(0, bracket_size - playoff_count)
    for _ in range(simulations):
        wins = dict(base_wins)
        for matchup in remaining:
            if matchup.roster_one not in wins or matchup.roster_two not in wins:
                continue
            chance = _game_probability(probabilities[matchup.roster_one], probabilities[matchup.roster_two])
            winner = matchup.roster_one if rng.random() < chance else matchup.roster_two
            wins[winner] += 1
        division_winners = []
        for group in divisions.values():
            if group:
                division_winners.append(max(group, key=lambda rid: (wins[rid], probabilities[rid], rng.random())))
        division_winners = sorted(set(division_winners), key=lambda rid: (wins[rid], probabilities[rid]), reverse=True)[:playoff_count]
        remaining_slots = max(0, playoff_count - len(division_winners))
        wildcard = sorted((rid for rid in ids if rid not in division_winners), key=lambda rid: (wins[rid], probabilities[rid]), reverse=True)[:remaining_slots]
        seeds = sorted(division_winners + wildcard, key=lambda rid: (wins[rid], probabilities[rid]), reverse=True)
        byes = seeds[:bye_count]
        for rid in seeds:
            counts[rid]["playoffs"] += 1
        for rid in division_winners:
            counts[rid]["division"] += 1
        for rid in byes:
            counts[rid]["bye"] += 1
        finalists, champion = _play_bracket(seeds, byes, probabilities, rng)
        for rid in finalists:
            counts[rid]["final"] += 1
        if champion is not None:
            counts[champion]["champion"] += 1


def _simulate_active(snapshot, probabilities, counts, simulations, rng) -> None:
    entrants = []
    eliminated = set()
    for row in snapshot.playoff_bracket:
        if not isinstance(row, dict):
            continue
        for key in ("t1", "t2", "w", "l"):
            value = row.get(key)
            if isinstance(value, int) and value not in entrants:
                entrants.append(value)
        if isinstance(row.get("l"), int):
            eliminated.add(row["l"])
    entrants = [rid for rid in entrants if rid in probabilities]
    alive = [rid for rid in entrants if rid not in eliminated]
    for rid in entrants:
        counts[rid]["playoffs"] = simulations
    if not alive:
        return
    for _ in range(simulations):
        finalists, champion = _play_bracket(sorted(alive, key=lambda rid: probabilities[rid], reverse=True), [], probabilities, rng)
        for rid in finalists:
            counts[rid]["final"] += 1
        if champion is not None:
            counts[champion]["champion"] += 1


def _play_bracket(seeds, byes, probabilities, rng):
    if not seeds:
        return [], None
    original_order = {rid: index for index, rid in enumerate(seeds)}
    round_teams = list(byes)
    pending = [rid for rid in seeds if rid not in byes]
    if len(pending) % 2:
        round_teams.append(pending.pop())
    for index in range(0, len(pending), 2):
        round_teams.append(_play_series(pending[index], pending[index + 1], probabilities, rng))
    round_teams.sort(key=lambda rid: original_order.get(rid, 999))
    while len(round_teams) > 2:
        round_teams = [_play_series(round_teams[i], round_teams[i + 1], probabilities, rng) for i in range(0, len(round_teams) - 1, 2)]
        round_teams.sort(key=lambda rid: original_order.get(rid, 999))
    if len(round_teams) == 1:
        return round_teams, round_teams[0]
    finalists = list(round_teams)
    return finalists, _play_series(round_teams[0], round_teams[1], probabilities, rng)


def _play_series(one, two, probabilities, rng):
    chance = _game_probability(probabilities[one], probabilities[two])
    return one if rng.random() < chance else two
