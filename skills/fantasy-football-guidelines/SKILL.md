---
name: fantasy-football-guidelines
description: Use when managing a Yahoo Fantasy or Sleeper roster, evaluating waiver or trade moves, or setting a weekly lineup through an authenticated platform.
---

# Fantasy Football Operations

Treat the fantasy platform as the source of truth for roster state, league settings, player eligibility, transaction rules, and lock times. Use current data. Never infer that a player is available, eligible, healthy, or unlocked.

## Platform support

- Yahoo Fantasy: use an authenticated Yahoo integration or UI. Confirm that the integration has Fantasy Sports read/write authorization before submitting mutations.
- Sleeper: the official API is read-only. Use it for inspection, then use an authenticated Sleeper UI or other write-capable integration for lineup and roster changes. Never claim that a Sleeper API call changed a team.
- Resolve each platform's own league, team, player, roster-slot, waiver, and lock identifiers. Do not transfer IDs or transaction assumptions between platforms.

## League profiles and scoring

When this repository is available, load `leagues/fantasy-leagues.toml` before analyzing a team. Select the profile by platform plus league ID or name, then apply its format, continuity, known rules, unknown rules, and strategy notes.

- Live platform settings are authoritative. Static profile values are user-provided context or verified overrides, not a substitute for a current settings read.
- Use the profile's statistics source for raw player stats. Normalize provider data to the profile's point template and calculate `sum(raw_stat * points_per_unit) + event_points + threshold_points`. Reconcile completed-game calculations against platform-reported fantasy points.
- If a required scoring rule is absent, do not fill it from a generic standard template. Report the missing rule or provide separate results for each plausible setting.
- For keeper leagues, include keeper eligibility, retention cost, and future value in roster and trade analysis. For stable long-running redraft leagues, use league history only as secondary evidence and do not assign keeper value. For the unverified Sleeper redraft PPR setting, branch on the configured candidates or fetch live settings before ranking players.
- When live settings establish a previously unknown value, report the profile fields that should be updated with the source and retrieval date. Do not silently rewrite the static file.

## Before acting

Identify the platform, league, scoring and roster settings, week, matchup, and user objective. Read the current roster, bench, IR, free-agent or waiver pool, opponent, and transaction state. Check injury status, bye weeks, expected participation, and lock times from current sources when relevant. Ask for a missing input when it could change the action.

## Decisions

- Optimize for the user's stated objective, such as this week's win or season-long value.
- Respect scoring, lineup limits, roster eligibility, injured reserve, keeper or dynasty rules, and league-specific transaction limits.
- State the cost and consequence of FAAB, waiver priority, drops, and trades. Projections and rankings are evidence, not guarantees.
- Label assumptions, uncertainty, and confidence when data conflicts or is stale.

## Transaction safety

- Draft the exact plan before submitting: add or claim, drop, trade, and bid or priority.
- Treat trades, drops, and paid claims as high-impact. Require confirmation of the exact players, parties, and amounts unless the user already authorized those bounds.
- A request to set a lineup authorizes lineup changes only. It does not authorize trades, drops, or waiver spend.
- Before submitting, re-check player names, team, week, slot, and lock status. After submitting, verify the resulting roster or lineup and report what changed or failed.
- If no authenticated write-capable platform is available, do not claim completion. Return the verified proposed actions and manual steps.

## Weekly lineup

Set a legal lineup. Check early-game lock times first. Prefer healthy, expected-to-play starters, and flag questionable players with a verified alternative. Do not override a locked player.

## Output

For advice, show the evidence and exact proposed changes. For executed actions, report the platform, league and week, result, costs, and unresolved risks. If ambiguity changes the outcome, stop and ask one focused question.
