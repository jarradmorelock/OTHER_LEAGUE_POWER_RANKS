"""Validate the checked-in league registry."""

from __future__ import annotations

import json
from pathlib import Path

from .models import LeagueConfig, Theme


QUARTERBACK_MODES = {"auto", "one_qb"}
LEAGUE_MODES = {"full", "offense_only_partial"}
MARKET_MODES = {"dynasty", "keeper_redraft"}
THEME_KEYS = {
    "background",
    "panel",
    "text",
    "muted",
    "market",
    "lineup",
    "season",
    "accent",
}
OPTIONAL_THEME_KEYS = {"defense"}


def load_leagues(path: Path) -> dict[str, LeagueConfig]:
    """Load profiles keyed by slug, rejecting ambiguous/unsafe configuration."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read league configuration {path}: {exc}") from exc
    records = raw.get("leagues") if isinstance(raw, dict) else None
    if not isinstance(records, dict) or not records:
        raise ValueError("Configuration must contain a non-empty 'leagues' object")

    output: dict[str, LeagueConfig] = {}
    league_ids: set[str] = set()
    webhook_envs: set[str] = set()
    for key, item in records.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(item, dict):
            raise ValueError(f"Invalid league entry: {key!r}")
        league_id = str(item.get("league_id") or "").strip()
        webhook_env = str(item.get("webhook_env") or "").strip()
        name = str(item.get("name") or "").strip()
        if not league_id or not webhook_env or not name:
            raise ValueError(f"League {key!r} is missing league_id, webhook_env, or name")
        if league_id in league_ids:
            raise ValueError(f"Configuration contains duplicate league_id {league_id!r}")
        if webhook_env in webhook_envs:
            raise ValueError(f"Configuration contains duplicate webhook_env {webhook_env!r}")
        league_ids.add(league_id)
        webhook_envs.add(webhook_env)

        quarterback_mode = str(item.get("quarterback_mode") or "auto")
        mode = str(item.get("mode") or "full")
        if quarterback_mode not in QUARTERBACK_MODES:
            raise ValueError(f"League {key!r} has unsupported quarterback_mode {quarterback_mode!r}")
        if mode not in LEAGUE_MODES:
            raise ValueError(f"League {key!r} has unsupported mode {mode!r}")
        colors = item.get("theme")
        if (
            not isinstance(colors, dict)
            or not THEME_KEYS.issubset(colors)
            or set(colors) - THEME_KEYS - OPTIONAL_THEME_KEYS
        ):
            raise ValueError(f"League {key!r} theme must define {sorted(THEME_KEYS)} and may define {sorted(OPTIONAL_THEME_KEYS)}")
        for color_key, value in colors.items():
            if not isinstance(value, str) or not value.startswith("#") or len(value) != 7:
                raise ValueError(f"League {key!r} theme color {color_key!r} must be #RRGGBB")
        expected_bonus = item.get("expected_bonus_rec_te")
        if expected_bonus is not None and not isinstance(expected_bonus, (int, float)):
            raise ValueError(f"League {key!r} expected_bonus_rec_te must be numeric or null")
        defense_weight = item.get("defense_weight", 0.0)
        market_mode = str(item.get("market_mode") or "dynasty")
        keeper_dynasty_share = item.get("keeper_dynasty_share", 1.0)
        if isinstance(defense_weight, bool) or not isinstance(defense_weight, (int, float)) or not 0 <= defense_weight < 1:
            raise ValueError(f"League {key!r} defense_weight must be numeric and between 0 inclusive and 1 exclusive")
        if market_mode not in MARKET_MODES:
            raise ValueError(f"League {key!r} has unsupported market_mode {market_mode!r}")
        if isinstance(keeper_dynasty_share, bool) or not isinstance(keeper_dynasty_share, (int, float)) or not 0 <= keeper_dynasty_share <= 1:
            raise ValueError(f"League {key!r} keeper_dynasty_share must be numeric and between 0 and 1")
        if market_mode == "dynasty" and float(keeper_dynasty_share) != 1.0:
            raise ValueError(f"League {key!r} dynasty market_mode requires keeper_dynasty_share=1.0")

        output[key] = LeagueConfig(
            key=key,
            league_id=league_id,
            name=name,
            brand=str(item.get("brand") or "OTHER LEAGUE").strip(),
            publication=str(item.get("publication") or name).strip(),
            quarterback_mode=quarterback_mode,
            webhook_env=webhook_env,
            mode=mode,
            expected_bonus_rec_te=float(expected_bonus) if expected_bonus is not None else None,
            theme=Theme(**colors),
            defense_weight=float(defense_weight),
            market_mode=market_mode,
            keeper_dynasty_share=float(keeper_dynasty_share),
        )
    return output
