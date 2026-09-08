import sqlite3
import unittest
from pathlib import Path


SCHEMA_PATH = Path(__file__).parents[1] / "fantasy_football" / "schema.sql"


class FantasyDataModelTests(unittest.TestCase):
    def test_schema_supports_provenance_scoring_and_decisions(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        connection.execute(
            "INSERT INTO source VALUES (?, ?, ?, ?, ?, ?)",
            ("sleeper", "Sleeper", "platform", "official", "https://docs.sleeper.com/", "on demand"),
        )
        observation = connection.execute(
            """
            INSERT INTO source_observation
                (source_id, retrieved_at, source_uri, entity_type, entity_key,
                 content_sha256, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING observation_id
            """,
            (
                "sleeper",
                "2026-09-08T15:00:00Z",
                "https://api.sleeper.app/v1/league/example",
                "league",
                "example",
                "abc123",
                '{"scoring_settings":{"rec":1}}',
            ),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO league VALUES (?, ?, ?, ?, ?)",
            ("workplace-sleeper-redraft", "Workplace Sleeper Redraft", "sleeper", "redraft", "leagues/fantasy-leagues.toml"),
        )
        league_season = connection.execute(
            """
            INSERT INTO league_season
                (league_id, season, platform_league_id)
            VALUES (?, ?, ?)
            RETURNING league_season_id
            """,
            ("workplace-sleeper-redraft", 2026, "example"),
        ).fetchone()[0]
        settings = connection.execute(
            """
            INSERT INTO league_settings_snapshot
                (league_season_id, source_observation_id, captured_at,
                 settings_json, scoring_settings_json, roster_positions_json, is_verified)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            RETURNING settings_snapshot_id
            """,
            (
                league_season,
                observation,
                "2026-09-08T15:00:00Z",
                "{}",
                '{"rec":1}',
                '["QB","RB","WR","TE","FLEX"]',
            ),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO scoring_rule (settings_snapshot_id, stat_key, rule_type, points) VALUES (?, ?, ?, ?)",
            (settings, "receptions", "per_unit", 1.0),
        )
        connection.execute(
            "INSERT INTO team VALUES (?, ?, ?, ?)",
            ("KC", "KC", "Kansas City Chiefs", "America/Chicago"),
        )
        connection.execute(
            "INSERT INTO fantasy_entity VALUES (?, ?, ?, ?, ?, ?)",
            ("player:example", "player", "Example Player", "WR", "KC", "{}"),
        )
        connection.execute(
            "INSERT INTO roster_snapshot VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, league_season, "1", "team", "2026-09-08T15:00:00Z", observation, "{}"),
        )
        connection.execute(
            "INSERT INTO roster_entity VALUES (?, ?, ?, ?, ?)",
            (1, "player:example", "WR", "starter", "123"),
        )
        run = "run-example"
        connection.execute(
            "INSERT INTO analysis_run VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run, league_season, 2026, 1, "win_this_week", "2026-09-08T15:00:00Z", "baseline_v1", "{}", "2026-09-08T15:00:00Z"),
        )
        connection.execute(
            "INSERT INTO decision (analysis_run_id, entity_id, decision_type, target_slot, rationale_json) VALUES (?, ?, ?, ?, ?)",
            (run, "player:example", "start", "WR", '{"evidence":["projection"]}'),
        )

        self.assertEqual(connection.execute("SELECT COUNT(*) FROM scoring_rule").fetchone()[0], 1)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM decision").fetchone()[0], 1)
        connection.close()


if __name__ == "__main__":
    unittest.main()
