"""Small data structures shared by the ranking pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Theme:
    background: str
    panel: str
    text: str
    muted: str
    market: str
    lineup: str
    season: str
    accent: str
    defense: str | None = None


@dataclass(frozen=True)
class LeagueConfig:
    key: str
    league_id: str
    name: str
    brand: str
    publication: str
    quarterback_mode: str
    webhook_env: str
    mode: str
    expected_bonus_rec_te: float | None
    theme: Theme
    defense_weight: float = 0.0


@dataclass(frozen=True)
class PlayerIdentity:
    sleeper_id: str
    name_id: str
    full_name: str
    position: str


@dataclass
class ValueBook:
    name: str
    category: str
    player_values: dict[str, float] = field(default_factory=dict)
    pick_values: dict[tuple[int, str, int], float] = field(default_factory=dict)
    scoring_adjusted: bool = False
    raw_projection: bool = False


@dataclass
class MarketBundle:
    players: dict[str, PlayerIdentity]
    books: list[ValueBook]
    warnings: list[str] = field(default_factory=list)

    @property
    def dynasty_books(self) -> list[ValueBook]:
        return [book for book in self.books if book.category == "dynasty"]

    @property
    def lineup_books(self) -> list[ValueBook]:
        return [book for book in self.books if book.category == "lineup"]

    @property
    def defense_books(self) -> list[ValueBook]:
        return [book for book in self.books if book.category == "defense"]


@dataclass(frozen=True)
class DraftPick:
    year: int
    round: int
    original_roster_id: int


@dataclass
class LeagueTeam:
    roster_id: int
    owner_id: str
    team_name: str
    owner_name: str
    player_ids: list[str]
    picks: list[DraftPick]
    wins: int
    losses: int
    ties: int
    points_for: float
    division: int = 0

    @property
    def games(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def record(self) -> str:
        if self.ties:
            return f"{self.wins}-{self.losses}-{self.ties}"
        return f"{self.wins}-{self.losses}"

    @property
    def win_percentage(self) -> float:
        if not self.games:
            return 0.5
        return (self.wins + self.ties * 0.5) / self.games


@dataclass(frozen=True)
class LeagueMatchup:
    week: int
    matchup_id: int
    roster_one: int
    roster_two: int
    points_one: float = 0.0
    points_two: float = 0.0


@dataclass
class LeagueSnapshot:
    league_id: str
    league_name: str
    season: int
    week: int
    is_superflex: bool
    ppr: float
    roster_positions: list[str]
    teams: list[LeagueTeam]
    scoring_settings: dict[str, float] = field(default_factory=dict)
    start_week: int = 1
    playoff_week_start: int = 15
    playoff_teams: int = 6
    divisions: int = 1
    playoff_round_type: int = 0
    league_average_match: bool = False
    matchups: list[LeagueMatchup] = field(default_factory=list)
    playoff_bracket: list[dict] = field(default_factory=list)
    idp_partial: bool = False
    warnings: list[str] = field(default_factory=list)
    defense_weight: float = 0.0


@dataclass
class RankedTeam:
    rank: int
    roster_id: int
    team_name: str
    owner_name: str
    record: str
    points_for: float
    score: float
    market_percentile: float
    lineup_percentile: float
    season_percentile: float | None
    market_points: float
    lineup_points: float
    season_points: float
    starter_rating: float
    previous_rank: int | None = None
    movement: int = 0
    record_guardrail_applied: bool = False
    source_ranks: dict[str, int] = field(default_factory=dict)
    projected_record: str = ""
    make_playoffs_pct: float = 0.0
    win_division_pct: float = 0.0
    first_round_bye_pct: float = 0.0
    make_final_pct: float = 0.0
    win_championship_pct: float = 0.0
    defense_percentile: float = 0.0
    defense_points: float = 0.0


@dataclass
class RankingResult:
    league: LeagueSnapshot
    teams: list[RankedTeam]
    dynasty_sources: list[str]
    lineup_sources: list[str]
    has_season_results: bool
    generated_at: str
    market_weight: float
    lineup_weight: float
    season_weight: float
    record_guardrail_active: bool
    forecast_simulations: int = 0
    forecast_model: str = ""
    warnings: list[str] = field(default_factory=list)
    defense_weight: float = 0.0
    defense_sources: list[str] = field(default_factory=list)
