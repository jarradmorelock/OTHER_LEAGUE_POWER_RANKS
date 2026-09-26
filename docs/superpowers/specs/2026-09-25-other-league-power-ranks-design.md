# Other League Power Ranks — Design Spec

**Status:** Draft for user review  
**Date:** 2026-09-25

## Goal and guardrails

Build a Saturday power-rankings publisher for six non-Ironbound Sleeper leagues. This is an independent repository and deployment: it must not modify, import code from, or share state with `Ironbound_power_ranks`. Adapt the proven model and visual conventions into this repository.

Each league gets one post in its own Discord Forum on Saturday, containing a power-rankings graphic and a championship/playoff-calculations graphic. Schedule at 15:00 UTC year-round, which lands between 10 a.m. and noon Eastern. Each league's movement compares with its prior Saturday ranking.

All six leagues are in the initial rollout. SEC may publish a clearly labeled partial ranking using supported offensive inputs while IDP support is developed. It must not imply IDP players, IDP lineup value, or IDP scoring were included until those inputs are integrated.

## League inventory

Sleeper league/roster/scoring settings are the runtime source of truth, with explicit per-league overrides only for confirmed differences.

| Key | League | Sleeper league ID | Observed format notes |
|---|---|---:|---|
| `broken_hearts` | Broken Hearts Fantasy Football League | `1391793948728492032` | 10 teams; 0.5 PPR; keeper setting; QB/RB/RB/WR/WR/TE/2 FLEX/DEF |
| `rocky_top_rumble` | Rocky Top Rumble | `1314710277232553984` | 6 teams; 0.5 PPR; keeper setting; QB/RB/RB/WR/WR/WR/TE/3 FLEX/SUPER_FLEX/DEF |
| `nine_to_five` | 9 to 5 | `1314710193413554176` | 10 teams; 0.5 PPR; keeper setting; QB/RB/RB/WR/WR/TE/2 FLEX/DEF |
| `best_characters` | Best Characters League | `1333195168139968512` | 16 teams; dynasty; TE premium (`bonus_rec_te=0.5`); SUPER_FLEX slot is 1QB-only; RB/WR/TE/3 FLEX/SUPER_FLEX |
| `sec` | Southeastern Conference (SEC) | `1341161857683058688` | 16 teams; dynasty; 1QB-only despite SUPER_FLEX slot; TE premium (`bonus_rec_te=1.5`); RB/RB/WR/WR/TE/FLEX/SUPER_FLEX/DL/LB/DB/2 IDP_FLEX; custom scoring |
| `dont_tell_my_wife` | Don't Tell My Wife I'm In This | `1341970851624402944` | 12 teams; dynasty; standard 1.0 PPR with no TE-premium bonus currently in Sleeper; QB/RB/RB/3 WR/TE/3 FLEX |

These observations are a starting snapshot, not hard-coded truth. Unexpected Sleeper setting changes should be reported rather than silently mis-modeled.

The Best Characters, Don't Tell My Wife, and SEC observations above were checked against Sleeper's live league endpoints on 2026-09-25: [Best Characters settings](https://api.sleeper.app/v1/league/1333195168139968512), [Don't Tell My Wife settings](https://api.sleeper.app/v1/league/1341970851624402944), and [SEC settings](https://api.sleeper.app/v1/league/1341161857683058688).

## Approaches considered

1. **Independent multi-league repository (selected):** one codebase/workflow with per-league configuration and state. It preserves isolation without maintaining six copies.
2. Six independent repositories/workflows: strongest per-league isolation, but duplicates fixes and upkeep.
3. Shared engine/package with the Ironbound repository: less duplication but couples releases and risks changing the system the user asked to preserve.

## Ranking and data flow

For each league, a run reads current Sleeper settings, rosters, actual record/points, schedule/results, and playoff configuration; fetches current player market values and current-season player ranking signals; computes rankings; simulates championship/playoff odds; renders two graphics; posts both in that league's Forum; and saves that league's prior-rank history after successful delivery.

Use the existing proven progressive model as baseline: before results, 45% market / 55% starters; weeks 1–3, 35% / 45% / 20% season results; weeks 4–7, 30% / 40% / 30%; week 8 onward, 25% / 35% / 40%. The season component is 80% record / 20% points-for, with the established record guardrail. Respect each league's lineup slots, 1QB/Superflex, PPR, team count, and dynasty/keeper status. Keep market and lineup signals distinct and report unavailable sources.

Use the internal playoff/championship simulator rather than requiring a Dynasty Daddy playoff-calculator scrape. The inherited model does not use weekly fantasy-point projections: it uses current market/ADP/ROS ranking signals plus actual Sleeper results. This limitation is documented in the README and run metadata.

The first three keeper leagues retain the same formula initially but use their real scoring/slots. Dynasty leagues use dynasty-market plus current-season starter signals. Apply `quarterback_mode=one_qb` for both Best Characters and SEC: in each, Sleeper's `SUPER_FLEX` label represents a QB-only slot in the intended 1QB format. Do not infer QB eligibility solely from the Sleeper slot string. Missing source coverage or a significant settings mismatch must not silently become zero values.

Scoring profiles must retain relevant Sleeper scoring modifiers, including PPR and `bonus_rec_te`. Best Characters currently has a 0.5 TE reception bonus; SEC has a 1.5 TE reception bonus (on top of its 1.0 base reception scoring). Don't Tell My Wife currently has no TE reception bonus in Sleeper, so treat it as standard 1.0 PPR unless the user confirms a different real-world setting. The data-source layer must not claim full TE-premium adaptation from a generic player ranking; it must either apply a validated scoring-aware adjustment or surface the limitation for review.

### SEC partial mode and future IDP support

Initial SEC mode publishes an **OFFENSE-ONLY / IDP NOT INCLUDED** ranking using only mapped offensive players and legal offensive lineup slots. Both graphics and the Discord post carry the disclosure. Do not count unmapped IDP players as zero while implying full-team value. The playoff simulator may use Sleeper standings/schedule and available offense-only strength, with the same disclosure.

SEC's current Sleeper scoring is substantially customized. The fetched configuration includes (among other settings): base reception 1.0 plus TE reception bonus 1.5; rushing TD 7, rushing attempt 0.3, receiving yard 0.1; passing TD 7, completion 0.3, attempt 0.1, incompletion -0.5; IDP solo tackle 2, assist 1, sack 5, tackle for loss 2, QB hit 0.5, pass defense 3, interception 6, forced fumble 3, fumble recovery 3, defensive TD 7, and safety 3, plus yardage and milestone bonuses. The complete live Sleeper `scoring_settings` object, not a hand-transcribed subset, is the implementation source of truth.

The IDP phase adds DL/LB/DB identity coverage, configurable scoring, and a legal lineup optimizer for DL, LB, DB, and IDP_FLEX slots, using SEC's complete Sleeper scoring settings. Remove the partial label only after coverage checks and tests show IDP players and slots participate in team scores. Prefer a stable feed or a transparent Sleeper-stat model; do not rely only on undocumented scraping.

## Discord delivery and secrets

Use a distinct incoming webhook per league. GitHub Actions secrets/configuration keys:

- `BROKEN_HEARTS_WEEKLY_WEBHOOK`
- `ROCKY_TOP_RUMBLE_WEEKLY_WEBHOOK`
- `NINE_TO_FIVE_WEEKLY_WEBHOOK`
- `BEST_CHARACTERS_WEEKLY_WEBHOOK`
- `SEC_WEEKLY_WEBHOOK`
- `DONT_TELL_MY_WIFE_WEEKLY_WEBHOOK`

Values are full Discord webhook URLs and must never appear in source files or logs. A successful post carries both graphics. Retry/report failures per league so one destination does not block the others.

## Schedule and state

One scheduled GitHub Actions workflow runs at 15:00 UTC each Saturday; manual dispatch supports testing/recovery. Maintain isolated per-league ranking history and last-success metadata. Update state only after both graphics are posted successfully. Make reruns idempotent per league/week: skip a league/week already posted unless explicitly forced, avoiding duplicate Forum posts and corrupt movement history.

No Tuesday delivery or email is in scope.

## Failure behavior

- Each league runs independently; a source, render, or Discord failure does not stop attempts for other leagues.
- Validate required secrets and minimum source coverage before posting.
- A league is not marked successful and its history is not advanced until both graphics are delivered.
- The workflow summary reports posted, partial, skipped, or failed per league with non-secret diagnostics.
- SEC partial mode is disclosed as partial, not represented as a complete IDP ranking.

## Validation

Checks cover: all six league IDs and distinct webhook keys; Sleeper settings/PPR/FLEX/SUPER_FLEX normalization; progressive weights and record influence on examples; Saturday-to-Saturday rank movement; deterministic playoff examples; both graphics and SEC labels; per-league failure isolation; state updates only after successful posts; webhook redaction; and SEC offense-only mode now plus legal IDP lineups before full mode.

Initial verification uses fixtures and manual dispatch without production webhooks. A separate smoke test can send to Discord only when the user is ready.

## Out of scope

- Any edits, imports, state, schedules, secrets, or deployments in `Ironbound_power_ranks`.
- Changes to Ironbound's Saturday/Tuesday/email system.
- Tuesday magazine delivery or email for these leagues.
- Claiming point-projection rankings or complete SEC IDP rankings before those capabilities exist.
