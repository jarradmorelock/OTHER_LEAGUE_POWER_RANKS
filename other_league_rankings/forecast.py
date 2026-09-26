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

    progress = _regular_season_progress(snapshot)
    team_count = len(snapshot.teams)
    playoff_count = min(team_count, max(2, snapshot.playoff_teams))
    bracket_size = 1 << (playoff_count - 1).bit_length()
    bye_count = max(0, bracket_size - playoff_count)
    division_sizes: dict[int, int] = {}
    if snapshot.divisions > 1:
        for league_team in snapshot.teams:
            if league_team.division > 0:
                division_sizes[league_team.division] = division_sizes.get(league_team.division, 0) + 1

    teams_by_id = {team.roster_id: team for team in snapshot.teams}
    for team in result.teams:
        values = counts[team.roster_id]
        league_team = teams_by_id[team.roster_id]
        team.projected_record = projected_records[team.roster_id]

        raw_playoffs = values["playoffs"] / simulations * 100
        raw_division = values["division"] / simulations * 100
        raw_bye = values["bye"] / simulations * 100
        raw_final = values["final"] / simulations * 100
        raw_champion = values["champion"] / simulations * 100

        playoff_baseline = playoff_count / team_count * 100
        division_baseline = (
            100 / division_sizes[league_team.division]
            if league_team.division in division_sizes
            else 0.0
        )
        bye_baseline = bye_count / team_count * 100
        final_baseline = min(2, team_count) / team_count * 100
        champion_baseline = 100 / team_count

        team.make_playoffs_pct = _confidence_adjust(raw_playoffs, playoff_baseline, progress)
        team.win_division_pct = _confidence_adjust(raw_division, division_baseline, progress)
        team.first_round_bye_pct = _confidence_adjust(raw_bye, bye_baseline, progress)
        team.make_final_pct = _confidence_adjust(raw_final, final_baseline, progress)
        team.win_championship_pct = _confidence_adjust(raw_champion, champion_baseline, progress)
    result.forecast_simulations = simulations
    result.forecast_model = f"{result.lineup_sources[0] if result.lineup_sources else 'starter values'} + Sleeper schedule · week-calibrated"


def _regular_season_progress(snapshot: LeagueSnapshot) -> float:
    regular_season_weeks = max(1, snapshot.playoff_week_start - snapshot.start_week)
    completed_weeks = max(0, min(regular_season_weeks, snapshot.week - snapshot.start_week))
    return completed_weeks / regular_season_weeks


def _confidence_adjust(raw_pct: float, baseline_pct: float, progress: float) -> float:
    """Apply week-based confidence bounds around the structural league baseline.

    At the start of the season the public forecast is a 50/50 blend of the
    Monte Carlo result and the event's neutral league-wide baseline. The raw
    model gains weight every week until it is used without shrinkage when the
    playoffs begin. Because raw probabilities are bounded at 0 and 100, this
    blend creates a natural floor and ceiling that relax every week without
    distorting the total probability mass for an event.
    """
    blend = 0.5 + 0.5 * max(0.0, min(1.0, progress))
    adjusted = baseline_pct + blend * (raw_pct - baseline_pct)
    return round(max(0.0, min(100.0, adjusted)), 1)


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
