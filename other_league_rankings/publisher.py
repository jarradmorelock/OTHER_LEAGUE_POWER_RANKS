"""Idempotent per-league Discord delivery and history advancement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any

from .discord import DiscordPublishError, DiscordWebhookPublisher
from .models import LeagueConfig, RankingResult
from .state import StateStore


class PublishError(RuntimeError):
    """A league could not be published safely."""


@dataclass(frozen=True)
class PublishResult:
    league_key: str
    status: str
    post_key: str
    message_id: str | None = None


def publish_league(
    config: LeagueConfig,
    result: RankingResult,
    image_paths: tuple[Path, Path],
    state: StateStore,
    dry_run: bool = True,
    *,
    webhook_url: str | None = None,
    discord: Any = None,
    force: bool = False,
) -> PublishResult:
    post_key = f"{result.league.season}-week-{result.league.week}"
    if dry_run:
        return PublishResult(config.key, "dry_run", post_key)
    current = state.load(config.key)
    if current.last_post_key == post_key and not force:
        return PublishResult(config.key, "skipped", post_key)
    selected_url = webhook_url if webhook_url is not None else os.environ.get(config.webhook_env, "")
    if not selected_url:
        raise PublishError(f"Missing Discord webhook secret {config.webhook_env}")
    if discord is None:
        discord = DiscordWebhookPublisher()
    week_label = f"Week {result.league.week}" if result.league.week else "Preseason"
    thread_name = f"{week_label} · {config.publication} · {result.league.season}"
    content = _forum_content(config, result)
    try:
        posted = discord.post_forum(selected_url, thread_name, content, image_paths)
    except DiscordPublishError as exc:
        raise PublishError(str(exc)) from None
    except Exception as exc:
        raise PublishError(f"Discord publication failed ({type(exc).__name__})") from None
    try:
        state.save_success(config.key, result, post_key)
    except Exception as exc:
        raise PublishError(f"Discord accepted the post but history could not be saved ({type(exc).__name__})") from None
    message_id = str(posted.get("id")) if isinstance(posted, dict) and posted.get("id") is not None else None
    return PublishResult(config.key, "posted", post_key, message_id)


def _forum_content(config: LeagueConfig, result: RankingResult) -> str:
    week_label = f"Week {result.league.week}" if result.league.week else "Preseason"
    parts = [f"**{config.brand} POWER RANKINGS — {week_label} {result.league.season}**"]
    if result.league.idp_partial:
        if result.defense_weight == 0:
            parts.append(
                "**OFFENSE-ONLY / IDP NOT INCLUDED** — the SEC schedule assigns 0% defense weight at this season stage."
            )
        else:
            parts.append(
                f"**IDP INCLUDED IN POWER RANKS ({result.defense_weight:.0%} weight)** using Sleeper's raw weekly `pts_ppr`; "
                "custom SEC IDP scoring and bonuses are not applied. Championship odds remain offense-only."
            )
    offense_label = "offense" if result.league.idp_partial else "starters"
    model_mix = (
        f"{result.market_weight:.0%} market / {result.lineup_weight:.0%} {offense_label} / "
        f"{result.defense_weight:.0%} defense / {result.season_weight:.0%} season results"
        if result.league.idp_partial or result.defense_weight > 0
        else f"{result.market_weight:.0%} market / {result.lineup_weight:.0%} starters / {result.season_weight:.0%} season results"
    )
    parts.append(f"Power rankings and championship calculations are attached. Model mix: {model_mix}.")
    if result.warnings:
        # Keep Forum copy actionable but compact; source diagnostics stay in the
        # workflow summary and generated image footers.
        parts.append("Source note: some ranking inputs may be incomplete; see the attached graphics for the sources used.")
    return "\n\n".join(parts)
