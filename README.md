# Other League Power Ranks

An independent Saturday publisher for six Sleeper leagues. It builds one image-first Discord Forum post per league containing a power-ranking graphic and a championship/playoff-odds graphic. It is intentionally separate from `Ironbound_power_ranks`; it neither imports that code nor shares its state or delivery schedule.

## Leagues and Discord secrets

Add these six repository secrets under **Settings → Secrets and variables → Actions**. Each value is the full incoming webhook URL for that league's Forum channel. Do not put webhook URLs in source files, workflow logs, or issues.

| League key | League | Required Actions secret |
| --- | --- | --- |
| `broken_hearts` | Broken Hearts Fantasy Football League | `BROKEN_HEARTS_WEEKLY_WEBHOOK` |
| `rocky_top_rumble` | Rocky Top Rumble | `ROCKY_TOP_RUMBLE_WEEKLY_WEBHOOK` |
| `nine_to_five` | 9 to 5 | `NINE_TO_FIVE_WEEKLY_WEBHOOK` |
| `best_characters` | Best Characters League | `BEST_CHARACTERS_WEEKLY_WEBHOOK` |
| `sec` | Southeastern Conference (SEC) | `SEC_WEEKLY_WEBHOOK` |
| `dont_tell_my_wife` | Don't Tell My Wife I'm In This | `DONT_TELL_MY_WIFE_WEEKLY_WEBHOOK` |

Best Characters and SEC are configured as QB-only even though Sleeper labels the additional slot `SUPER_FLEX`. The run reads current roster and scoring settings from Sleeper; configuration contains only confirmed overrides and display settings. A mismatch in the expected TE reception bonus is reported in the run output.

## Schedule and operation

GitHub Actions runs every Saturday at **15:00 UTC** (11 a.m. Eastern during daylight time and 10 a.m. during standard time). It tests the code, attempts each league independently, and uploads generated graphics as an artifact. A failure for one league does not prevent the others from being attempted.

After a successful Discord post, the workflow saves that league's rank history in `state/<league-key>.json` and commits the state update. The per-league files track previous rank and last successful post, so movement is Saturday-to-Saturday and reruns skip a league/week already posted unless forced. State advances only after Discord confirms the post containing both images.

Manual workflow dispatch defaults to a dry run. Select a league or all six; check **publish** only when you intend to post. `force` permits an intentional duplicate/recovery post. Generated dry-run previews appear in the workflow artifact. Local preview and publication commands:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m other_league_rankings --league all --dry-run
python -m other_league_rankings --league sec --publish
```

Dry-run images are written under `exports/<league-key>/`. The CLI defaults to dry-run; `--publish` is required for Discord delivery. Add `--force` only when a duplicate post is intended, or `--week N` to override Sleeper's reported week for a recovery run.

## Ranking and source model

Broken Hearts, Rocky Top Rumble, and 9 to 5 are redraft/keeper leagues, so their market component is **80% current redraft value and 20% dynasty value**. The smaller dynasty share preserves keeper equity without letting long-term dynasty value dominate a one-season power ranking. Best Characters, SEC, and Don't Tell My Wife remain dynasty-market leagues.

For every league, the forward-looking lineup component is now **ROS scoring** rather than a static player-rank lineup. For each remaining fantasy week through Week 17, Sleeper player projections are rescored with that league's own offensive scoring settings, the engine selects the best legal lineup for that week, and those weekly lineup totals are averaged. That naturally incorporates byes, weekly role changes, depth, and league-specific scoring. If projection coverage is unavailable, the existing Dynasty Daddy/FantasyCalc starter-ranking path remains a fallback rather than silently scoring missing projections as zero.

The non-SEC weight schedule moves toward real results every completed NFL week. League-median wins do not make the model age twice as fast.

| Completed NFL weeks | Market | ROS scoring | Season results |
| ---: | ---: | ---: | ---: |
| Preseason | 45.0% | 55.0% | 0.0% |
| 1 | 35.0% | 45.0% | 20.0% |
| 2 | 33.6% | 43.6% | 22.9% |
| 3 | 32.1% | 42.1% | 25.7% |
| 4 | 30.7% | 40.7% | 28.6% |
| 5 | 29.3% | 39.3% | 31.4% |
| 6 | 27.9% | 37.9% | 34.3% |
| 7 | 26.4% | 36.4% | 37.1% |
| 8+ | 25.0% | 35.0% | 40.0% |

The season-results component itself is unchanged: 80% win percentage (ties count as half a win) and 20% points-for percentile. The four-or-more-win-gap guardrail begins after eight completed NFL weeks and still caps an extreme lower-record lead at ten score points.

SEC keeps its separate four-part offense/IDP structure, but its weights now interpolate every week from Week 1 to Week 8 instead of jumping in broad buckets. Week 1 begins at 30% market / 35% ROS offense / 20% results / 15% defense; Week 8 reaches 20% / 30% / 40% / 10%. The defense input remains Sleeper's raw weekly `pts_ppr`; custom SEC IDP bonuses are intentionally not applied.

Dynasty Daddy still provides the dynasty-market feeds (KeepTradeCut, FantasyCalc, DynastyProcess, and DynastySuperflex). FantasyCalc Direct provides the redraft market feed for the three keeper/redraft leagues. Sleeper provides the weekly ROS projections, which are rescored with each league's scoring settings. The engine reports unavailable feeds, projection gaps, and fallback use explicitly.

## SEC IDP integration

SEC's power rankings now include a separate **Defense** component sourced from Sleeper weekly IDP `pts_ppr` projections. The graphic and post state that raw provider values are used and SEC custom IDP bonuses are not applied. Championship odds still use the offense-only strength signal. This is SEC-only; all other league charts and scoring are unchanged.

The SEC-only defense schedule activates only with a mapped Sleeper projection source and legal DL/LB/DB/IDP_FLEX slots; if coverage fails while the scheduled weight is nonzero, that league run fails safely rather than publishing a silently offense-only ranking. The raw weekly projection route is undocumented and may change, so the post identifies it as a provider projection, not a league-scoring calculation.

## Development checks

The tests use fake Sleeper and ranking-source responses; they do not post to Discord. Coverage includes configuration, normalized scoring and records, source fallbacks, QB-only SUPER_FLEX handling, progressive record weights, guardrails, movement, deterministic playoff examples, both rendered PNGs, SEC disclosure, state isolation, webhook redaction, idempotency, and league failure isolation. A live-data dry run is the final pre-publication smoke check; it produces graphics but never sends a webhook.
