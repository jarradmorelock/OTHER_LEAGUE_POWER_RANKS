# Other League Power Ranks Implementation Plan

> **For agentic workers:** Implement this plan task-by-task with `superpowers:executing-plans`. Each step is checked only after its stated test passes.

**Goal:** Independently publish Saturday power-ranking and championship-odds graphics for six Sleeper leagues to six Discord Forums, with disclosed offense-only SEC output until IDP ranking inputs are validated.

**Architecture:** Build a standalone Python package in this repository, adapting the proven Ironbound ranking workflow without importing from or modifying it. A league registry supplies settings and a distinct webhook per league; Sleeper and rankings sources feed the shared engine; independent league runs render two images, publish, then update only that league's history.

**Tech Stack:** Python 3.11, `requests`, `matplotlib`, GitHub Actions, `unittest`, JSON configuration and publication state.

**Spec:** `docs/superpowers/specs/2026-09-25-other-league-power-ranks-design.md`

## Global Constraints

- Keep this repository and deployment independent; do not import from or modify `Ironbound_power_ranks`.
- Publish one Saturday Discord Forum post per league with both graphics.
- Run the schedule at 15:00 UTC every Saturday and support manual dry-run dispatch.
- Keep movement history isolated by league and advance it only after a successful post.
- Preserve the model weights: 45/55/0 preseason; 35/45/20 through week 3; 30/40/30 weeks 4–7; 25/35/40 week 8 onward.
- Set Best Characters and SEC to 1QB despite Sleeper's `SUPER_FLEX` slot.
- Use Sleeper's current scoring/roster settings as source of truth; disclose unavailable or unsupported scoring inputs.
- SEC's initial report is **OFFENSE-ONLY / IDP NOT INCLUDED**; no unmodeled IDP assets may be presented as full-team value.
- Keep these leagues' Tuesday/email delivery out of scope.
- Leave changes uncommitted for the user to stage and commit in GitHub Desktop.

## Review Focus

- Sleeper changes a league's roster slots or scoring after configuration; runtime validation must warn/fail that league instead of silently misranking it. Test in Task 2.
- A Sleeper `SUPER_FLEX` slot is intended to be QB-only in Best Characters and SEC; test the override against an RB eligible for generic SF. Test in Task 4.
- Source rankings omit many custom scoring modifiers, especially TE-premium bonuses; expose a source/scoring limitation rather than imply exact scoring adaptation. Test in Task 3.
- One webhook fails or a rerun occurs after some leagues posted; continue other leagues, avoid duplicate posts, and only advance successful league state. Test in Task 6.
- SEC's offense-only partial mode sees IDP-heavy rosters; exclude IDP from score math and prominently disclose the limitation in both graphics and Forum text. Test in Task 4 and Task 5.

---

## File Map

- `pyproject.toml`, `requirements.txt`: package metadata, Python/dependency bounds, and test discovery.
- `other_league_rankings/models.py`: immutable league configuration plus snapshot/result dataclasses.
- `other_league_rankings/config.py`, `leagues.json`: six league profiles, modes, colors, QB overrides, and webhook environment-variable names.
- `other_league_rankings/http.py`, `sleeper.py`: bounded-retry HTTP client and Sleeper league/roster/record/schedule snapshot adapter.
- `other_league_rankings/sources.py`: Dynasty Daddy and direct FantasyCalc ranking feeds, player identity mapping, and coverage warnings.
- `other_league_rankings/engine.py`: source normalization, legal lineup evaluation, progressive weights, season component, rank movement.
- `other_league_rankings/forecast.py`: deterministic playoff/championship simulation adapted from the current engine.
- `other_league_rankings/render.py`: two graph exports per league, including partial-mode labels.
- `other_league_rankings/state.py`: per-league state, movement history, and duplicate-publication keys.
- `other_league_rankings/discord.py`, `publisher.py`: webhook validation, two-image Forum posts, per-league error isolation.
- `other_league_rankings/runner.py`, `__main__.py`: dry-run/publish orchestration and CLI.
- `.github/workflows/publish.yml`: Saturday schedule, dry-run/manual inputs, tests, artifact upload, and state persistence.
- `README.md`: setup, six required secrets, Saturday behavior, model limits, test/dry-run procedure.
- `tests/`: focused unit and integration tests for each component.

## Interfaces

- `load_leagues(path: Path) -> dict[str, LeagueConfig]`
- `fetch_snapshot(client: HttpClient, config: LeagueConfig, week: int | None = None) -> LeagueSnapshot`
- `fetch_rankings(client: HttpClient, config: LeagueConfig, snapshot: LeagueSnapshot) -> MarketBundle`
- `rank_league(snapshot: LeagueSnapshot, bundle: MarketBundle, previous_ranks: dict[str, int] | None = None) -> RankingResult`
- `attach_forecast(result: RankingResult, simulations: int = 10_000) -> None`
- `render_result(result: RankingResult, output_dir: Path) -> tuple[Path, Path]`
- `publish_league(config: LeagueConfig, result: RankingResult, image_paths: tuple[Path, Path], state: StateStore, dry_run: bool) -> PublishResult`
- `run(configs: dict[str, LeagueConfig], selected: str = "all", dry_run: bool = True, force: bool = False) -> RunSummary`

Every run returns a per-league status; one league's exception is captured and does not abort the others.

### Task 1: Python package and league configuration

**Files:** Create package/config/model files above; create `tests/test_config.py`, `tests/test_models.py`, `pyproject.toml`, and `requirements.txt`.

**Interfaces:** Produce `LeagueConfig`, `LeagueSnapshot`, `LeagueTeam`, `PlayerIdentity`, `ValueBook`, and `RankingResult`; expose `load_leagues(path)`.

- [ ] **Step 1: Write failing tests for six distinct league profiles.** In `test_config.py`, add `test_loads_six_unique_profiles`, `test_best_characters_and_sec_are_one_qb`, `test_webhook_keys_are_unique`, and `test_duplicate_league_ids_are_rejected`. For example:

```python
class ConfigTests(unittest.TestCase):
    def test_best_characters_and_sec_are_one_qb(self):
        leagues = load_leagues(Path("leagues.json"))
        self.assertEqual(leagues["best_characters"].quarterback_mode, "one_qb")
        self.assertEqual(leagues["sec"].quarterback_mode, "one_qb")
```

- [ ] **Step 2: Run `python -m unittest tests.test_config -v`; confirm it fails because the package/config are absent.**
- [ ] **Step 3: Add configuration parsing and validation.** Parse league IDs as strings; reject duplicate IDs, duplicate webhook env names, empty names, unsupported modes, and missing theme colors. Implement `load_leagues(path)` as a pure parser that returns a key-indexed dict and raises `ValueError` naming the invalid key.
- [ ] **Step 4: Add `leagues.json` entries for all six leagues.** Set SEC mode to `offense_only_partial`; preserve the observed PPR/TE premium scoring metadata, and mark DTMYI as standard PPR according to current Sleeper settings.
- [ ] **Step 5: Run `python -m unittest tests.test_config tests.test_models -v`; confirm all six profiles load and invalid profiles fail with specific messages.**

### Task 2: Sleeper snapshot and normalized settings

**Files:** Create `http.py`, `sleeper.py`; create `tests/test_sleeper.py` and fixtures in `tests/fixtures/sleeper/`.

**Interfaces:** `fetch_snapshot(client, config, week=None)` returns current league/season/week, scoring settings, exact roster slots, teams/owners, players, wins/losses/ties, points-for, schedule/matchups, divisions, and playoff format.

- [ ] **Step 1: Write fixture tests for one keeper league, Best Characters, and SEC.** Add `test_keeps_all_sec_scoring_keys`, `test_best_characters_superflex_slot_is_preserved`, `test_normalizes_records_and_owners`, and `test_rejects_missing_rosters`. For example:

```python
class SleeperTests(unittest.TestCase):
    def test_keeps_all_sec_scoring_keys(self):
        snapshot = normalize_league_payload(self.sec_league_payload, config_for("sec"))
        self.assertEqual(snapshot.scoring_settings["idp_sack"], 5.0)
        self.assertEqual(snapshot.scoring_settings["bonus_rec_te"], 1.5)
        self.assertIn("idp_def_td", snapshot.scoring_settings)
```

- [ ] **Step 2: Run `python -m unittest tests.test_sleeper -v`; confirm missing adapter errors.**
- [ ] **Step 3: Implement the bounded-retry client and public Sleeper endpoints.** Inject transport into tests; retry network/429/5xx with capped exponential delay; do not retry invalid league IDs or malformed JSON. Keep the interface `HttpClient.get_json(path: str) -> dict | list`; `fetch_snapshot` should call this client, not raw `requests`.
- [ ] **Step 4: Normalize Sleeper payloads without dropping custom scoring keys.** Reject missing teams or roster settings, preserve `bonus_rec_te`, IDP settings, roster slots, and standings fields unchanged.
- [ ] **Step 5: Run `python -m unittest tests.test_sleeper -v`; add a mismatch test proving unexpected required slots/settings produce a league-level warning rather than an assumed default.**

### Task 3: Current ranking sources and scoring-signal coverage

**Files:** Create `sources.py`; create `tests/test_sources.py`; extend `models.py` for source coverage/warnings.

**Interfaces:** `fetch_rankings(client, config, snapshot)` returns a `MarketBundle` with distinct dynasty-market and current-season lineup books, mapped Sleeper player IDs, source names, and warnings.

- [ ] **Step 1: Write fake-response tests for Dynasty Daddy's four market feeds, metadata/ADP/ROS fields, pick normalization, fallback to FantasyCalc, and source failures.** Add `test_maps_market_values_to_sleeper_ids`, `test_ros_is_a_lineup_signal`, `test_falls_back_to_fantasycalc_when_primary_feed_missing`, and `test_generic_rank_warns_for_te_premium`. Example:

```python
class SourceTests(unittest.TestCase):
    def test_generic_rank_warns_for_te_premium(self):
        bundle = fetch_rankings(self.fake_client, config_for("best_characters"), self.snapshot)
        self.assertTrue(any("TE premium" in warning for warning in bundle.warnings))
        self.assertFalse(bundle.lineup_books[0].scoring_adjusted)
```

- [ ] **Step 2: Run `python -m unittest tests.test_sources -v`; confirm the source adapter is absent.**
- [ ] **Step 3: Implement the feeds behind injectable `HttpClient`; map source names to Sleeper IDs and keep dynasty and lineup values separate.** Preserve the names and categories of successfully loaded feeds in `MarketBundle`; never turn an unavailable feed into an empty but successful book.
- [ ] **Step 4: Add coverage checks by league and by relevant roster positions.** For SEC's current mode, require offensive player coverage only and emit a specific `IDP_NOT_INCLUDED` warning; do not turn unidentified defenders into zero-value entries.
- [ ] **Step 5: Run `python -m unittest tests.test_sources -v`; test direct FantasyCalc fallback and the case where no valid lineup source remains.**

### Task 4: Ranking engine, formats, progressive record weighting, and movement

**Files:** Create `engine.py`; create `tests/test_engine.py`; extend config/model tests.

**Interfaces:** `rank_league(snapshot, bundle, previous_ranks=None)` returns ordered teams with component scores, record, source coverage, prior rank, and partial-data status.

- [ ] **Step 1: Write deterministic example tests.** Add `test_weight_schedule`, `test_season_score_is_record_weighted`, `test_record_guardrail_caps_roster_lead`, and `test_movement_uses_previous_saturday_rank`. Cover all four weight stages, 80/20 record/points season scoring, the record guardrail, and rank movement from 2 to 4. Example:

```python
class EngineTests(unittest.TestCase):
    def test_weight_schedule(self):
        self.assertEqual(ranking_weights(0), (0.45, 0.55, 0.0))
        self.assertEqual(ranking_weights(3), (0.35, 0.45, 0.20))
        self.assertEqual(ranking_weights(5), (0.30, 0.40, 0.30))
        self.assertEqual(ranking_weights(8), (0.25, 0.35, 0.40))
```

- [ ] **Step 2: Write format tests.** An RB may fill a generic Superflex slot, but cannot fill the QB-only replacement slot in Best Characters or SEC; TE-premium metadata remains visible as unsupported unless a compatible value signal is present.
- [ ] **Step 3: Run `python -m unittest tests.test_engine -v`; confirm it fails before engine implementation.**
- [ ] **Step 4: Implement source percentiles, legal offensive lineup calculation, configured quarterback mode, progressive weights, season component, and guardrail.** Normalize a `SUPER_FLEX` slot to `QB` when `quarterback_mode == "one_qb"`. For SEC partial mode, calculate only mapped offensive roster/lineup signals and tag the result `offense_only_partial`.
- [ ] **Step 5: Run `python -m unittest tests.test_engine -v`; verify changing a team's W-L record in a fixture changes its rank as the season weight grows.**

### Task 5: Championship simulation and graphics

**Files:** Create `forecast.py`, `render.py`; create `tests/test_forecast.py`, `tests/test_render.py`.

**Interfaces:** `attach_forecast(result, simulations=10000)` annotates each ranked team with projected record/playoff/division/bye/final/championship rates; `render_result(result, output_dir)` writes ranking and odds PNGs and returns both paths.

- [ ] **Step 1: Write fixed-seed tests for schedule projection, playoff qualification, active bracket simulation, and probability bounds.** Add `test_forecast_is_repeatable`, `test_playoff_odds_stay_between_zero_and_one`, `test_playoff_odds_are_monotonic_for_two_team_fixture`, and `test_active_bracket_excludes_eliminated_teams`. Example:

```python
class ForecastTests(unittest.TestCase):
    def test_forecast_is_repeatable(self):
        result = make_two_team_result()
        attach_forecast(result, simulations=500)
        first = [team.win_championship_pct for team in result.teams]
        attach_forecast(result, simulations=500)
        self.assertEqual(first, [team.win_championship_pct for team in result.teams])
```

- [ ] **Step 2: Run `python -m unittest tests.test_forecast -v`; confirm the simulator is not yet implemented.**
- [ ] **Step 3: Adapt the existing deterministic simulator to the new snapshot/result models; seed by league ID, season, week, and iteration count.**
- [ ] **Step 4: Write image tests that open both PNGs, assert dimensions/content count, verify component/record labels and movement arrows, and require SEC disclosure on each image.**
- [ ] **Step 5: Implement the two-graph visual layout and run `python -m unittest tests.test_forecast tests.test_render -v`; visually inspect fixture output before delivery.**

### Task 6: Persistent history and independent Discord Forum publication

**Files:** Create `state.py`, `discord.py`, `publisher.py`; create `tests/test_state.py`, `tests/test_discord.py`, `tests/test_publisher.py`.

**Interfaces:** `StateStore.load(league_key: str) -> LeagueState` returns prior ranks and last post key; `StateStore.save_success(league_key, result, post_key)` atomically advances state; `publish_league(...)` posts both files and saves state only after success.

- [ ] **Step 1: Write tests for six isolated state files, movement restoration, idempotent same-week behavior, and atomic save after successful publication only.** Add `test_state_paths_are_isolated_by_league`, `test_previous_ranks_are_loaded`, `test_same_week_post_is_skipped`, and `test_failure_does_not_advance_history`. Example:

```python
class PublisherTests(unittest.TestCase):
    def test_failure_does_not_advance_history(self):
        with self.assertRaises(PublishError):
            self.publisher.publish(self.result)
        self.assertEqual(self.fake_state.load("sec").rank_by_roster_id, {})
```

- [ ] **Step 2: Write fake-session tests for missing/invalid webhook URLs, Forum post payload with two attachments, retryable HTTP failures, and redaction.**
- [ ] **Step 3: Run `python -m unittest tests.test_state tests.test_discord tests.test_publisher -v`; confirm failures precede implementation.**
- [ ] **Step 4: Implement atomic JSON state and validated webhook publishing.** Read only the configured per-league environment variable; never log the URL. Skip previously successful league/week unless `force` is explicitly true.
- [ ] **Step 5: Test a six-league batch where one webhook fails.** Verify five successful posts update five histories, the failed league remains retryable, and the runner still reports every league.

### Task 7: Runner, CLI, scheduled workflow, and operator documentation

**Files:** Create `runner.py`, `__main__.py`, `.github/workflows/publish.yml`; update `README.md`; create `tests/test_runner.py`, `tests/test_schedule.py`.

**Interfaces:** CLI supports `--league all|<key>`, `--dry-run`, `--publish`, `--force`, and optional `--week`; runner returns one status per selected league.

- [ ] **Step 1: Write runner tests using fake clients, renderers, and publisher.** Add `test_dry_run_never_calls_webhook`, `test_failed_league_does_not_stop_batch`, and `test_single_league_selection`. Check one failed league does not stop later league attempts. Example:

```python
class RunnerTests(unittest.TestCase):
    def test_failed_league_does_not_stop_batch(self):
        self.fake_services.publisher.fail_for = {"sec"}
        summary = run(self.six_configs, selected="all", dry_run=False)
        self.assertEqual(summary.statuses["sec"].state, "failed")
        self.assertEqual(summary.statuses["dont_tell_my_wife"].state, "posted")
```

- [ ] **Step 2: Run `python -m unittest tests.test_runner tests.test_schedule -v`; confirm it fails before orchestration/workflow exists.**
- [ ] **Step 3: Implement CLI and per-league orchestration.** A dry run writes both images/JSON under `exports/<league>/` and leaves publication state unchanged.
- [ ] **Step 4: Add GitHub Actions Saturday schedule `0 15 * * 6`, manual dry-run/publish/force inputs, Python 3.11 setup, dependency install, test run, artifact upload, and success-state commit/push using workflow permissions.** Map the six `*_WEEKLY_WEBHOOK` secrets one-to-one to config names.
- [ ] **Step 5: Document all six secret names, dry-run instructions, output artifacts, model weights, lack of fantasy-point projections, per-league failure behavior, and SEC partial disclosure. Run the full test suite and confirm a local fixture-only `--dry-run --league all` produces 12 images without network or Discord access.**

## Completion Criteria

- All six league configurations validate and use the confirmed QB-only exceptions for Best Characters and SEC.
- Each selected league can independently produce both graphics from fixtures and a live-data dry run.
- SEC labels both images and Forum text as offense-only/IDP not included in the initial implementation.
- A Saturday publication sends one post per league, with two graphics, and preserves successful rank history without cross-league contamination.
- A failed league does not prevent the other five from being attempted.
- The existing Ironbound repository and workflows remain unchanged.
- All automated tests pass; production posting is only enabled when the user chooses it.
