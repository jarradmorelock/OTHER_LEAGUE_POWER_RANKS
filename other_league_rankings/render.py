"""Render gallery-friendly ranking and championship probability graphics."""

from __future__ import annotations

from pathlib import Path
import unicodedata

from .models import LeagueConfig, RankingResult


def render_result(result: RankingResult, config: LeagueConfig, output_dir: Path) -> tuple[Path, Path]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        import matplotlib.patheffects as path_effects
    except ImportError as exc:
        raise RuntimeError("Matplotlib is required to render ranking graphics") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    ranking_path = output_dir / "power-rankings.png"
    odds_path = output_dir / "championship-odds.png"
    theme = config.theme
    disclosure = _disclosure(result)

    teams = result.teams
    fig, ax = plt.subplots(figsize=(11, max(8, 0.48 * len(teams) + 3)), dpi=160)
    _style_chart(fig, ax, theme, len(teams))
    y = list(range(len(teams)))
    market = [team.market_points for team in teams]
    lineup = [team.lineup_points for team in teams]
    season = [team.season_points for team in teams]
    defense = [team.defense_points for team in teams]
    has_projection_ros = any("ROS scoring projections" in source for source in result.lineup_sources)
    offense_label = (
        "ROS offense" if result.league.idp_partial and has_projection_ros
        else "Offense" if result.league.idp_partial
        else "ROS scoring" if has_projection_ros
        else "Current starters"
    )
    ax.barh(y, market, color=theme.market, height=0.62, label=result.market_label)
    ax.barh(y, lineup, left=market, color=theme.lineup, height=0.62, label=offense_label)
    if result.league.idp_partial or result.defense_weight > 0:
        defense_label = f"Defense ({result.defense_weight:.0%} weight)"
        if result.league.idp_partial and result.defense_weight == 0:
            defense_label = "Defense (0.0 placeholder)"
        ax.barh(y, defense, left=[a + b for a, b in zip(market, lineup)], color=theme.defense or theme.accent, height=0.62, label=defense_label)
    if result.has_season_results:
        ax.barh(y, season, left=[a + b + c for a, b, c in zip(market, lineup, defense)], color=theme.season, height=0.62, label="Season results")
    for index, team in enumerate(teams):
        components = [team.market_points, team.lineup_points]
        if result.league.idp_partial or result.defense_weight > 0:
            components.append(team.defense_points)
        if result.has_season_results:
            components.append(team.season_points)
        _component_labels(ax, index, components, theme.text, theme.background, path_effects)
        ax.text(min(105, team.score + 1), index, f"{team.score:.1f}", va="center", ha="left", color=theme.text, fontsize=8.5, fontweight="bold")
        if result.league.idp_partial and result.defense_weight == 0:
            ax.text(116, index, f"{team.defense_points:.1f}", va="center", ha="center", color=theme.muted, fontsize=7.5, fontweight="bold")
        ax.text(-1.5, index + 0.28, f"{team.record}  |  {_safe(team.owner_name)[:22]}", va="top", ha="right", color=theme.muted, fontsize=6.5, clip_on=False)
    ax.set_yticks(y, [_rank_label(team) for team in teams], color=theme.text, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 122 if result.league.idp_partial and result.defense_weight == 0 else 108)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    if result.league.idp_partial and result.defense_weight == 0:
        ax.text(116, -0.58, "DEF", va="center", ha="center", color=theme.muted, fontsize=7, fontweight="bold")
    _header(fig, config, result, "POWER RANKINGS", disclosure, theme, Rectangle)
    legend_columns = 4 if (result.league.idp_partial or result.defense_weight > 0) and result.has_season_results else 3 if result.has_season_results else 2
    ax.legend(loc="lower left", bbox_to_anchor=(0, -0.15), ncol=legend_columns, frameon=False, fontsize=8, labelcolor=theme.muted)
    market_detail = (
        "market (80% redraft / 20% dynasty)"
        if result.market_label == "Roster market"
        else "dynasty market"
    )
    formula_parts = [f"{result.market_weight:.0%} {market_detail}", f"{result.lineup_weight:.0%} {offense_label.lower()}"]
    if result.league.idp_partial or result.defense_weight > 0:
        formula_parts.append(f"{result.defense_weight:.0%} defense")
    if result.has_season_results:
        formula_parts.append(f"{result.season_weight:.0%} season (80% record / 20% points)")
        formula = "  ·  ".join(formula_parts)
    elif not (result.league.idp_partial or result.defense_weight > 0):
        formula = f"{result.market_weight:.0%} {market_detail}  ·  {result.lineup_weight:.0%} {offense_label.lower()}  ·  preseason"
    else:
        formula = "  ·  ".join(formula_parts) + "  ·  preseason"
    _footer(fig, result, theme, formula)
    components_description = (
        f"Dynasty market, Offense, Defense ({result.defense_weight:.0%} weight), Season results"
        if result.defense_weight > 0
        else "Dynasty market, Offense, Defense (0.0 placeholder), Season results"
    )
    description = f"{disclosure}; components: {components_description}" if disclosure else "Power rankings"
    fig.savefig(ranking_path, facecolor=fig.get_facecolor(), metadata={"Description": description})
    plt.close(fig)

    odds_teams = sorted(teams, key=lambda team: (team.make_playoffs_pct, team.win_championship_pct, -team.rank), reverse=True)
    fig, ax = plt.subplots(figsize=(11, max(8, 0.48 * len(odds_teams) + 3)), dpi=160)
    _style_chart(fig, ax, theme, len(odds_teams))
    y = list(range(len(odds_teams)))
    playoff = [team.make_playoffs_pct for team in odds_teams]
    champion = [team.win_championship_pct for team in odds_teams]
    ax.barh([p - 0.16 for p in y], playoff, color=theme.market, height=0.28, label="Make playoffs")
    ax.barh([p + 0.16 for p in y], champion, color=theme.lineup, height=0.28, label="Win championship")
    for index, team in enumerate(odds_teams):
        _odds_label(ax, team.make_playoffs_pct, index - 0.16, f"{team.make_playoffs_pct:.0f}%", theme, path_effects)
        _odds_label(ax, team.win_championship_pct, index + 0.16, f"{team.win_championship_pct:.0f}%", theme, path_effects)
        ax.text(-1.5, index + 0.31, f"Proj {team.projected_record or team.record}  ·  Division {team.win_division_pct:.0f}%  ·  Bye {team.first_round_bye_pct:.0f}%", va="top", ha="right", color=theme.muted, fontsize=6.2, clip_on=False)
    ax.set_yticks(y, [f"{i:>2}.  {_safe(team.team_name)[:27]}" for i, team in enumerate(odds_teams, 1)], color=theme.text, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 108)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    _header(fig, config, result, "CHAMPIONSHIP ODDS", disclosure, theme, Rectangle)
    ax.legend(loc="lower left", bbox_to_anchor=(0, -0.15), ncol=2, frameon=False, fontsize=8, labelcolor=theme.muted)
    _footer(fig, result, theme, f"{result.forecast_simulations:,} simulations · {result.forecast_model}")
    fig.savefig(odds_path, facecolor=fig.get_facecolor(), metadata={"Description": disclosure or "Championship odds"})
    plt.close(fig)
    return ranking_path, odds_path


def _style_chart(fig, ax, theme, team_count):
    fig.patch.set_facecolor(theme.background)
    ax.set_facecolor(theme.background)
    fig.subplots_adjust(left=0.34, right=0.93, top=0.76, bottom=0.23)
    ax.tick_params(axis="x", colors=theme.muted, labelsize=8, length=0)
    ax.tick_params(axis="y", colors=theme.text, length=0, pad=11)
    ax.xaxis.grid(True, color=theme.panel, linewidth=1, alpha=0.85)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)


def _header(fig, config, result, title, disclosure, theme, rectangle):
    fig.text(0.06, 0.94, config.brand, color=theme.text, fontsize=30, fontweight="bold", va="top")
    fig.text(0.06, 0.885, title, color=theme.accent, fontsize=15, fontweight="bold", va="top")
    issue = f"WEEK {result.league.week} · {result.league.season}" if result.league.week else f"PRESEASON · {result.league.season}"
    fig.text(0.94, 0.93, issue, color=theme.text, fontsize=11, fontweight="bold", ha="right", va="top")
    fig.text(0.94, 0.895, config.publication, color=theme.muted, fontsize=8, ha="right", va="top")
    fig.add_artist(rectangle((0.06, 0.85), 0.88, 0.004, transform=fig.transFigure, color=theme.accent, linewidth=0))
    if disclosure:
        fig.text(0.5, 0.825, disclosure, color=theme.accent, fontsize=9, fontweight="bold", ha="center", va="top")


def _footer(fig, result, theme, detail):
    fig.text(0.06, 0.07, detail, color=theme.text, fontsize=7.2, ha="left")
    fig.text(0.06, 0.042, f"Sources: {', '.join(result.dynasty_sources + result.lineup_sources)} · Sleeper", color=theme.muted, fontsize=6.1, ha="left")


def _component_labels(ax, y, values, color, outline, path_effects):
    left = 0.0
    for value in values:
        if value > 0:
            narrow = value < 4.5
            ax.text(left + value / 2, y, f"{value:.1f}", ha="center", va="center", rotation=90 if narrow else 0, fontsize=5.6 if narrow else 6.8, fontweight="bold", color=color, path_effects=[path_effects.withStroke(linewidth=1.6, foreground=outline)], clip_on=True)
        left += value


def _odds_label(ax, value, y, label, theme, path_effects):
    inside = value >= 14
    ax.text(value / 2 if inside else value + 1, y, label, ha="center" if inside else "left", va="center", fontsize=7, fontweight="bold", color=theme.text, clip_on=True, path_effects=[path_effects.withStroke(linewidth=1.3, foreground=theme.background)])


def _rank_label(team):
    movement = "NEW" if team.previous_rank is None else (f"↑{team.movement}" if team.movement > 0 else f"↓{abs(team.movement)}" if team.movement < 0 else "—")
    return f"{team.rank:>2}.  {_safe(team.team_name)[:27]}   {movement}"


def _safe(value: str) -> str:
    replacements = {"卄": "H", "🅱️": "B", "🅱": "B", "™": ""}
    for source, replacement in replacements.items():
        value = value.replace(source, replacement)
    return unicodedata.normalize("NFKC", value).encode("ascii", "ignore").decode("ascii").strip()


def _disclosure(result: RankingResult) -> str:
    if result.league.idp_partial:
        if result.defense_weight == 0:
            return "OFFENSE-ONLY / IDP NOT INCLUDED · DEFENSE WEIGHT 0% AT THIS SEASON STAGE"
        return f"IDP INCLUDED IN POWER RANKS · DEFENSE {result.defense_weight:.0%} WEIGHT · RAW SLEEPER PTS_PPR · SEC BONUSES NOT APPLIED · ODDS OFFENSE-ONLY"
    return ""
