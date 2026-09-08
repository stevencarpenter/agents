---
name: fantasy-football-guidelines
description: Use when inspecting a Yahoo Fantasy or Sleeper roster, evaluating waiver or trade moves, or recommending a weekly lineup.
---

# Fantasy Football Operations

Treat the fantasy platform as the source of truth for roster state, league settings, player eligibility, transaction rules, and lock times. Use current data. Never infer that a player is available, eligible, healthy, or unlocked.

## Platform support

- Yahoo Fantasy: use the authenticated Yahoo Fantasy API for inspection. Treat this agent as read-only; the user performs final lineup and roster changes in Yahoo.
- Sleeper: the official API is read-only. Use it for inspection, then provide manual lineup and roster steps for the user. Never claim that a Sleeper API call changed a team.
- Resolve each platform's own league, team, player, roster-slot, waiver, and lock identifiers. Do not transfer IDs or transaction assumptions between platforms.

## League profiles and scoring

When this repository is available, load `leagues/fantasy-leagues.toml` before analyzing a team. Select the profile by platform plus league ID or name, then apply its format, continuity, known rules, unknown rules, and strategy notes.

- Live platform settings are authoritative. Static profile values are user-provided context or verified overrides, not a substitute for a current settings read.
- Use the profile's statistics source for raw player stats. Normalize provider data to the profile's point template and calculate `sum(raw_stat * points_per_unit) + event_points + threshold_points`. Reconcile completed-game calculations against platform-reported fantasy points.
- If a required scoring rule is absent, do not fill it from a generic standard template. Report the missing rule or provide separate results for each plausible setting.
- For keeper leagues, include keeper eligibility, retention cost, and future value in roster and trade analysis. For stable long-running redraft leagues, use league history only as secondary evidence and do not assign keeper value. For the unverified Sleeper redraft PPR setting, branch on the configured candidates or fetch live settings before ranking players.
- When live settings establish a previously unknown value, report the profile fields that should be updated with the source and retrieval date. Do not silently rewrite the static file.

## Data model and evidence

When the data store is available, use `fantasy_football/schema.sql` as the canonical boundary.

- Treat `source_observation` as immutable provenance. Keep the source URI, retrieval time, effective time, and content hash with every raw payload. A correction creates a new observation.
- Resolve players, team defenses, and platform identifiers through `fantasy_entity` and `entity_id_map`. Do not join Yahoo, Sleeper, nflverse, and NFL identifiers by display name.
- Use `league_settings_snapshot` and `scoring_rule` for exact scoring. Every calculated score and projection must name its settings snapshot and calculation or model version.
- Use `game_stat` for player and team facts, `context_event` for weather, availability, practice, depth-chart, news, and market observations, and `roster_snapshot` for current and historical eligibility.
- Build `player_week_feature` rows from only observations available at the feature `as_of` time. Include opponent defensive performance, teammate role and competition, snaps, routes, targets, red-zone usage, pace, game environment, weather, injuries, and credible news as typed features or feature JSON. Store feature lineage.
- Use `fantasy_points` to calculate deterministic league points and reconcile them to platform-reported points. Use `projection`, `analysis_run`, and `decision` for versioned forecasts and auditable start, bench, add, drop, claim, and trade recommendations. Use `projection_evaluation` for backtesting without mutating the original forecast.
- Do not let an unverified media claim override platform or official injury information. Store public-news claims with source, time, confidence, and materiality, and use only the availability-relevant effect in the model.
- Enforce an analysis cutoff. Do not use post-lock news, final scores, later stat corrections, or future roster state in a pregame recommendation.
- Use platform data for league rules, roster ownership, eligibility, locks, and reported fantasy points. Use nflverse for weekly stats, play-by-play, snap counts, depth charts, schedules, and available Next Gen Stats. Use the NWS API for stadium weather forecasts. Use official NFL or team reports for availability when a provider feed is missing or stale. Use media as corroborating evidence and extract only time-stamped, confidence-scored events.
- Keep player role and interaction features explicit: opponent defensive efficiency, teammate competition, route and snap share, red-zone usage, team pace, game environment, weather, and availability. Features must be computed from the information known at their cutoff, and the model must preserve the feature lineage used for the recommendation.

Preferred tooling for the first implementation is Python standard-library ingestion and SQLite for the control plane, Parquet for raw and derived analytical data, and DuckDB for local analytical queries. Add Polars when dataframe transforms become the bottleneck. Start with a calibrated, interpretable baseline model and add a heavier model only after as-of backtests demonstrate an improvement.

## Before acting

Identify the platform, league, scoring and roster settings, week, matchup, and user objective. Read the current roster, bench, IR, free-agent or waiver pool, opponent, and transaction state. Check injury status, bye weeks, expected participation, and lock times from current sources when relevant. Ask for a missing input when it could change the action.

## Decisions

- Optimize for the user's stated objective, such as this week's win or season-long value.
- Respect scoring, lineup limits, roster eligibility, injured reserve, keeper or dynasty rules, and league-specific transaction limits.
- State the cost and consequence of FAAB, waiver priority, drops, and trades. Projections and rankings are evidence, not guarantees.
- Label assumptions, uncertainty, and confidence when data conflicts or is stale.

## Transaction safety

- Draft the exact plan before submitting: add or claim, drop, trade, and bid or priority.
- Treat trades, drops, and paid claims as high-impact. State the exact players, parties, and amounts for the user to review.
- A request to set a lineup authorizes a recommendation only. It does not authorize the agent to submit trades, drops, or waiver spend.
- Before presenting a plan, re-check player names, team, week, slot, and lock status. Return the verified proposed actions and manual platform steps.
- Never claim an external mutation succeeded. If the user reports making a change, re-read platform state before relying on it.

## Weekly lineup

Set a legal lineup. Check early-game lock times first. Prefer healthy, expected-to-play starters, and flag questionable players with a verified alternative. Do not override a locked player.

## Output

For advice, show the evidence and exact proposed changes. For executed actions, report the platform, league and week, result, costs, and unresolved risks. If ambiguity changes the outcome, stop and ask one focused question.
