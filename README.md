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

The non-SEC leagues use this progressively record-aware model:

| Season stage | Dynasty market | Current starters | Season results |
| --- | ---: | ---: | ---: |
| Preseason | 45% | 55% | 0% |
| Weeks 1–3 | 35% | 45% | 20% |
| Weeks 4–7 | 30% | 40% | 30% |
| Week 8 onward | 25% | 35% | 40% |

The season-results component is 80% win percentage (ties count as half a win) and 20% points-for percentile. After eight games, a four-or-more-win-gap guardrail caps a lower-record team's lead over the better-record teams at ten score points. Current starters are evaluated in legal offensive lineup slots; a one-QB league's `SUPER_FLEX` slot is treated as QB-only.

SEC has a separate four-part schedule. The defense input is Sleeper's raw weekly `pts_ppr`; custom SEC IDP bonuses are intentionally not applied. Preseason keeps the existing 45% market / 55% offense split until weekly projections are available.

| SEC season stage | Market | Offense | Results | Defense |
| --- | ---: | ---: | ---: | ---: |
| Weeks 1–3 | 30% | 35% | 20% | 15% |
| Weeks 4–7 | 25% | 32% | 30% | 13% |
| Week 8 onward | 20% | 30% | 40% | 10% |

Dynasty Daddy provides the available market feeds (KeepTradeCut, FantasyCalc, DynastyProcess, and DynastySuperflex) and current ROS starter ranks; preseason starter ranks use ADP. If either dynasty-market or current-season input is unavailable, direct FantasyCalc values are used as fallback where available. The engine reports unavailable feeds, mapping gaps, and scoring limitations instead of representing missing sources as a successful zero-value feed. Generic player rankings are **not** scoring-adjusted for TE-premium bonuses. The weekly calculations also do not use weekly fantasy-point projections; they combine current player rankings with actual Sleeper records and points-for.

## SEC IDP integration

SEC's power rankings now include a separate **Defense** component sourced from Sleeper weekly IDP `pts_ppr` projections. The graphic and post state that raw provider values are used and SEC custom IDP bonuses are not applied. Championship odds still use the offense-only strength signal. This is SEC-only; all other league charts and scoring are unchanged.

The SEC-only defense schedule activates only with a mapped Sleeper projection source and legal DL/LB/DB/IDP_FLEX slots; if coverage fails while the scheduled weight is nonzero, that league run fails safely rather than publishing a silently offense-only ranking. The raw weekly projection route is undocumented and may change, so the post identifies it as a provider projection, not a league-scoring calculation.

## Development checks

The tests use fake Sleeper and ranking-source responses; they do not post to Discord. Coverage includes configuration, normalized scoring and records, source fallbacks, QB-only SUPER_FLEX handling, progressive record weights, guardrails, movement, deterministic playoff examples, both rendered PNGs, SEC disclosure, state isolation, webhook redaction, idempotency, and league failure isolation. A live-data dry run is the final pre-publication smoke check; it produces graphics but never sends a webhook.
