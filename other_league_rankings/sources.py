"""Fetch dynasty-market and current-season player-ranking signals."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

from .http import DataSourceError
from .models import LeagueConfig, LeagueSnapshot, MarketBundle, PlayerIdentity, ValueBook


DYNASTY_DADDY_BASE = "https://dynasty-daddy.com/api/v1"
FANTASY_CALC_URL = "https://api.fantasycalc.com/values/current"
MARKET_FEEDS = ((0, "KeepTradeCut"), (1, "FantasyCalc"), (2, "DynastyProcess"), (3, "DynastySuperflex"))
OFFENSE_POSITIONS = {"QB", "RB", "WR", "TE"}
IDP_POSITIONS = {"DL", "DE", "DT", "NT", "EDGE", "LB", "ILB", "OLB", "DB", "CB", "S", "FS", "SS"}
UNAVAILABLE_STATUSES = {"PUP", "IR", "SUS", "COV"}
MINIMUM_MAPPED_PLAYERS = 25


def fetch_rankings(client: Any, config: LeagueConfig, snapshot: LeagueSnapshot) -> MarketBundle:
    """Load DD signals where available, with FantasyCalc as a category fallback."""
    warnings: list[str] = []
    books: list[ValueBook] = []
    identities: dict[str, PlayerIdentity] = {}
    try:
        primary = fetch_dynasty_daddy(client, is_superflex=snapshot.is_superflex, week=snapshot.week)
        identities.update(primary.players)
        books.extend(primary.books)
        warnings.extend(primary.warnings)
    except DataSourceError as exc:
        warnings.append(f"Dynasty Daddy unavailable: {exc}")

    existing_categories = {book.category for book in books if book.player_values}
    missing = {"dynasty", "lineup"} - existing_categories
    if missing:
        try:
            fallback = fetch_fantasy_calc(
                client,
                is_superflex=snapshot.is_superflex,
                num_teams=len(snapshot.teams),
                ppr=snapshot.ppr,
            )
            identities.update(fallback.players)
            warnings.extend(fallback.warnings)
            for book in fallback.books:
                if book.category in missing:
                    books.append(book)
            for category in sorted(missing):
                warnings.append(f"Using direct FantasyCalc values as a {category} fallback.")
        except DataSourceError as exc:
            warnings.append(f"FantasyCalc fallback unavailable: {exc}")

    for category in ("dynasty", "lineup"):
        if not any(book.category == category and book.player_values for book in books):
            raise DataSourceError(f"No usable {category} value source was available for {config.key}")

    if config.expected_bonus_rec_te is not None and config.expected_bonus_rec_te > 0:
        if not any(book.scoring_adjusted for book in books if book.category == "lineup"):
            warnings.append(
                f"TE premium ({config.expected_bonus_rec_te:g} bonus reception points) is not incorporated by generic player rankings."
            )
    _augment_rostered_identities(client, snapshot, identities)

    rostered_offense = {
        player_id
        for team in snapshot.teams
        for player_id in team.player_ids
        if identities.get(player_id) and identities[player_id].position in OFFENSE_POSITIONS
    }
    missing_identity_count = sum(
        1 for team in snapshot.teams for player_id in team.player_ids
        if player_id not in identities
    )
    if missing_identity_count:
        warnings.append(
            f"{missing_identity_count} rostered players lack a source identity mapping and are omitted, not scored as zero."
        )
    if not rostered_offense:
        warnings.append("No rostered offensive players were identity-mapped by the selected ranking sources.")
    if config.mode == "offense_only_partial":
        defense_book, defense_warnings = fetch_sleeper_idp_projections(client, snapshot, identities)
        warnings.extend(defense_warnings)
        if defense_book is not None:
            books.append(defense_book)
    return MarketBundle(players=identities, books=books, warnings=warnings)


def fetch_sleeper_idp_projections(
    client: Any,
    snapshot: LeagueSnapshot,
    players: dict[str, PlayerIdentity],
) -> tuple[ValueBook | None, list[str]]:
    """Map weekly IDP projections using Sleeper's raw provider pts_ppr value."""
    url = f"https://api.sleeper.app/v1/projections/nfl/regular/{snapshot.season}/{snapshot.week}"
    try:
        payload = client.get_json(url)
    except DataSourceError as exc:
        return None, [f"Sleeper IDP projections unavailable: {exc}"]
    if not isinstance(payload, dict):
        return None, ["Sleeper IDP projections returned an invalid payload; defense remains disabled."]

    projections: dict[str, dict[str, Any]] = {}
    for sleeper_id, row in payload.items():
        identity = players.get(str(sleeper_id))
        if identity is None or identity.position not in IDP_POSITIONS or not isinstance(row, dict):
            continue
        stats = row.get("stats") if isinstance(row.get("stats"), dict) else row
        if _number(stats.get("gp")) <= 0:
            continue
        projections[str(sleeper_id)] = stats
    if not projections:
        return None, ["Sleeper returned no mapped, playable IDP projections; defense remains disabled."]

    book = ValueBook(
        name="Sleeper IDP weekly projections (raw pts_ppr)",
        category="defense",
        raw_projection=True,
    )
    for sleeper_id, stats in projections.items():
        if "pts_ppr" in stats:
            book.player_values[sleeper_id] = _number(stats["pts_ppr"])
    if not book.player_values:
        return None, ["Sleeper returned no mapped IDP projections with pts_ppr values; defense remains disabled."]
    return book, [
        "SEC defense inputs use Sleeper's raw weekly pts_ppr projections; custom SEC IDP scoring and bonuses are intentionally not applied."
    ]


def _augment_rostered_identities(client: Any, snapshot: LeagueSnapshot, identities: dict[str, PlayerIdentity]) -> None:
    """Use Sleeper's public player catalog to distinguish omitted IDP from offense."""
    missing = {
        pid for team in snapshot.teams for pid in team.player_ids
        if pid not in identities
    }
    if not missing:
        return
    cached = getattr(client, "_other_league_sleeper_identities", None)
    if cached is None:
        try:
            catalog = client.get_json("https://api.sleeper.app/v1/players/nfl")
        except DataSourceError:
            return
        cached = {}
        if isinstance(catalog, dict):
            for sleeper_id, row in catalog.items():
                if not isinstance(row, dict):
                    continue
                position = str(row.get("position") or "").upper().strip()
                first = str(row.get("first_name") or "").strip()
                last = str(row.get("last_name") or "").strip()
                name = str(row.get("full_name") or f"{first} {last}".strip() or sleeper_id)
                if position:
                    cached[str(sleeper_id)] = PlayerIdentity(
                        str(sleeper_id), _name_id(name, position), name, position
                    )
        try:
            setattr(client, "_other_league_sleeper_identities", cached)
        except (AttributeError, TypeError):
            pass
    for sleeper_id in missing:
        if sleeper_id in cached:
            identities[sleeper_id] = cached[sleeper_id]


def fetch_dynasty_daddy(client: Any, *, is_superflex: bool, week: int) -> MarketBundle:
    metadata = client.get_json(f"{DYNASTY_DADDY_BASE}/player/all/today")
    if not isinstance(metadata, list) or len(metadata) < MINIMUM_MAPPED_PLAYERS:
        raise DataSourceError("Dynasty Daddy returned incomplete player metadata")
    by_name: dict[str, PlayerIdentity] = {}
    players: dict[str, PlayerIdentity] = {}
    asset_names: dict[str, str] = {}
    for row in metadata:
        if not isinstance(row, dict):
            continue
        name_id = str(row.get("name_id") or "").strip()
        sleeper_id = str(row.get("sleeper_id") or "").strip()
        name = str(row.get("full_name") or name_id).strip()
        position = str(row.get("position") or "").upper().strip()
        if name_id:
            asset_names[name_id] = name
        if sleeper_id and name_id:
            identity = PlayerIdentity(sleeper_id, name_id, name, position)
            players[sleeper_id] = identity
            by_name[name_id] = identity

    value_field = "sf_trade_value" if is_superflex else "trade_value"
    books: list[ValueBook] = []
    warnings: list[str] = []
    for market_id, label in MARKET_FEEDS:
        try:
            rows = client.get_json(f"{DYNASTY_DADDY_BASE}/player/all/market/{market_id}")
            books.append(_dynasty_book(rows, label, value_field, by_name, asset_names))
        except DataSourceError as exc:
            warnings.append(f"{label} unavailable: {exc}")
    metric = "avg_ros" if week > 0 else "avg_adp"
    label = "Dynasty Daddy ROS" if metric == "avg_ros" else "Dynasty Daddy ADP"
    lineup = ValueBook(name=label, category="lineup")
    for row in metadata:
        if not isinstance(row, dict):
            continue
        sleeper_id = str(row.get("sleeper_id") or "").strip()
        position = str(row.get("position") or "").upper().strip()
        status = str(row.get("injury_status") or "").upper().strip()
        if not sleeper_id or position not in OFFENSE_POSITIONS or status in UNAVAILABLE_STATUSES:
            continue
        ranking = _number(row.get(metric))
        if ranking > 0:
            # Higher scores mean a better current starter ranking; the engine
            # will percentile-normalize books across teams.
            lineup.player_values[sleeper_id] = max(1.0, 500.0 - ranking)
    if len(lineup.player_values) >= MINIMUM_MAPPED_PLAYERS:
        books.append(lineup)
    else:
        warnings.append(f"Dynasty Daddy {metric.upper()} starter rankings had too few mapped players.")
    return MarketBundle(players=players, books=books, warnings=warnings)


def fetch_fantasy_calc(client: Any, *, is_superflex: bool, num_teams: int, ppr: float) -> MarketBundle:
    players: dict[str, PlayerIdentity] = {}
    books: list[ValueBook] = []
    warnings: list[str] = []
    for is_dynasty, label, category in (
        (True, "FantasyCalc Direct", "dynasty"),
        (False, "FantasyCalc Redraft Direct", "lineup"),
    ):
        query = urlencode({
            "isDynasty": str(is_dynasty).lower(),
            "numQbs": 2 if is_superflex else 1,
            "numTeams": num_teams,
            "ppr": ppr,
        })
        try:
            rows = client.get_json(f"{FANTASY_CALC_URL}?{query}")
        except DataSourceError as exc:
            warnings.append(f"{label} unavailable: {exc}")
            continue
        if not isinstance(rows, list):
            warnings.append(f"{label} returned an invalid payload")
            continue
        book = ValueBook(name=label, category=category)
        for row in rows:
            if not isinstance(row, dict):
                continue
            player = row.get("player") or {}
            value = _number(row.get("value"))
            sleeper_id = str(player.get("sleeperId") or "").strip()
            name = str(player.get("name") or "").strip()
            position = str(player.get("position") or "").upper().strip()
            if sleeper_id and name and value > 0:
                players[sleeper_id] = PlayerIdentity(sleeper_id, _name_id(name, position), name, position)
                book.player_values[sleeper_id] = value
            elif value > 0:
                pick = parse_pick_asset(name)
                if pick:
                    book.pick_values[pick] = value
        if len(book.player_values) < MINIMUM_MAPPED_PLAYERS:
            warnings.append(f"{label} returned too few mapped players")
            continue
        books.append(book)
    if not books:
        raise DataSourceError("FantasyCalc returned no usable dynasty or lineup source")
    return MarketBundle(players=players, books=books, warnings=warnings)


def _dynasty_book(rows: Any, label: str, field: str, identities: dict[str, PlayerIdentity], assets: dict[str, str]) -> ValueBook:
    if not isinstance(rows, list):
        raise DataSourceError(f"{label} returned an invalid payload")
    book = ValueBook(name=label, category="dynasty")
    for row in rows:
        if not isinstance(row, dict):
            continue
        name_id = str(row.get("name_id") or "").strip()
        value = _number(row.get(field))
        if not name_id or value <= 0:
            continue
        identity = identities.get(name_id)
        if identity:
            book.player_values[identity.sleeper_id] = value
        else:
            pick = parse_pick_asset(assets.get(name_id, ""))
            if pick:
                book.pick_values[pick] = value
    if len(book.player_values) < MINIMUM_MAPPED_PLAYERS:
        raise DataSourceError(f"{label} returned too few mapped players")
    return book


def parse_pick_asset(name: str) -> tuple[int, str, int] | None:
    match = re.search(r"\b(20\d{2})\s+(Early|Mid|Late)\s+([1-9])(?:st|nd|rd|th)\b", name, flags=re.IGNORECASE)
    return (int(match.group(1)), match.group(2).lower(), int(match.group(3))) if match else None


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _name_id(name: str, position: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower()) + position.lower()
