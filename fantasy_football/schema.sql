-- Fantasy football storage boundary.
--
-- Keep this control-plane schema small and append-only. Raw provider payloads
-- live in source_observation. The normalized columns below are the stable join
-- keys used by the agent. Timestamps are ISO-8601 UTC strings.
--
-- Use SQLite for league state, scoring snapshots, provenance, and decisions.
-- Keep large historical stats and play-by-play in Parquet and query them with
-- DuckDB. Do not copy the analytical lake into this database by default.

PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

CREATE TABLE source (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'platform', 'stats', 'weather', 'news', 'market', 'derived'
    )),
    authority TEXT NOT NULL,
    base_url TEXT NOT NULL,
    freshness_policy TEXT NOT NULL
);

-- One immutable payload or response from one source. Never overwrite a row when
-- a provider corrects data. Insert a new observation with a new content hash.
CREATE TABLE source_observation (
    observation_id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source(source_id),
    retrieved_at TEXT NOT NULL,
    published_at TEXT,
    effective_at TEXT,
    source_uri TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE (source_id, source_uri, content_sha256)
);

CREATE TABLE league (
    league_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('yahoo', 'sleeper')),
    league_format TEXT NOT NULL CHECK (league_format IN ('redraft', 'keeper')),
    profile_path TEXT NOT NULL
);

-- Platform identifiers can change by season. Keep them here instead of on the
-- long-lived league profile.
CREATE TABLE league_season (
    league_season_id INTEGER PRIMARY KEY,
    league_id TEXT NOT NULL REFERENCES league(league_id),
    season INTEGER NOT NULL,
    platform_league_id TEXT,
    platform_team_id TEXT,
    platform_user_id TEXT,
    status TEXT,
    UNIQUE (league_id, season)
);

-- Every exact calculation must name the settings snapshot it used. This keeps
-- historical scoring correct when a commissioner changes a league rule.
CREATE TABLE league_settings_snapshot (
    settings_snapshot_id INTEGER PRIMARY KEY,
    league_season_id INTEGER NOT NULL REFERENCES league_season(league_season_id),
    source_observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id),
    captured_at TEXT NOT NULL,
    effective_from TEXT,
    effective_to TEXT,
    settings_json TEXT NOT NULL,
    scoring_settings_json TEXT NOT NULL,
    roster_positions_json TEXT NOT NULL,
    is_verified INTEGER NOT NULL DEFAULT 0 CHECK (is_verified IN (0, 1))
);

-- stat_key is the canonical normalized stat name, not a Yahoo or Sleeper key.
-- For per-unit and event rules, points are awarded for raw_value / unit_size.
-- Threshold and custom rules carry their additional semantics in rule_json.
CREATE TABLE scoring_rule (
    scoring_rule_id INTEGER PRIMARY KEY,
    settings_snapshot_id INTEGER NOT NULL REFERENCES league_settings_snapshot(settings_snapshot_id),
    stat_key TEXT NOT NULL,
    rule_type TEXT NOT NULL CHECK (rule_type IN ('per_unit', 'event', 'threshold', 'custom')),
    points REAL NOT NULL,
    unit_size REAL NOT NULL DEFAULT 1 CHECK (unit_size > 0),
    threshold_operator TEXT,
    threshold_value REAL,
    rule_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE team (
    team_id TEXT PRIMARY KEY,
    abbreviation TEXT NOT NULL,
    display_name TEXT NOT NULL,
    timezone TEXT
);

-- Includes ordinary players and team-defense fantasy assets. Team defense is
-- represented as an entity while its actual defensive stats remain team rows
-- in game_stat.
CREATE TABLE fantasy_entity (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('player', 'team_defense')),
    display_name TEXT NOT NULL,
    position TEXT NOT NULL,
    team_id TEXT REFERENCES team(team_id),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- Namespaces include nflverse, gsis, yahoo, and sleeper. A mapping is also
-- timestamped because platform identifiers and provider mappings are inputs.
CREATE TABLE entity_id_map (
    mapping_id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES fantasy_entity(entity_id),
    namespace TEXT NOT NULL,
    external_id TEXT NOT NULL,
    source_observation_id INTEGER REFERENCES source_observation(observation_id),
    observed_at TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE venue (
    venue_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    timezone TEXT
);

CREATE TABLE game (
    game_id TEXT PRIMARY KEY,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    season_type TEXT NOT NULL,
    kickoff_at TEXT NOT NULL,
    home_team_id TEXT NOT NULL REFERENCES team(team_id),
    away_team_id TEXT NOT NULL REFERENCES team(team_id),
    venue_id TEXT REFERENCES venue(venue_id),
    game_status TEXT NOT NULL,
    source_observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id)
);

-- One fact table supports player stats and team defensive/offensive stats while
-- preserving the common game/week/source dimensions. Exactly one subject key is
-- populated per row.
CREATE TABLE game_stat (
    game_stat_id INTEGER PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES game(game_id),
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    player_entity_id TEXT REFERENCES fantasy_entity(entity_id),
    team_id TEXT REFERENCES team(team_id),
    stat_scope TEXT NOT NULL CHECK (stat_scope IN (
        'player', 'offense', 'defense', 'special_teams', 'all'
    )),
    source_observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id),
    stat_status TEXT NOT NULL CHECK (stat_status IN ('partial', 'final', 'corrected')),
    stat_json TEXT NOT NULL,
    CHECK (
        (player_entity_id IS NOT NULL AND team_id IS NULL)
        OR (player_entity_id IS NULL AND team_id IS NOT NULL)
    )
);

-- Typed event envelope for weather, availability, practice, depth chart, news,
-- market, and other context. event_json contains the source-specific fields;
-- confidence is the only universally comparable field.
CREATE TABLE context_event (
    context_event_id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('player', 'team', 'game', 'league')),
    entity_id TEXT,
    game_id TEXT REFERENCES game(game_id),
    source_observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id),
    event_type TEXT NOT NULL,
    published_at TEXT,
    effective_at TEXT,
    observed_at TEXT NOT NULL,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    event_json TEXT NOT NULL,
    CHECK (entity_id IS NOT NULL OR game_id IS NOT NULL)
);

CREATE TABLE roster_snapshot (
    roster_snapshot_id INTEGER PRIMARY KEY,
    league_season_id INTEGER NOT NULL REFERENCES league_season(league_season_id),
    platform_roster_id TEXT NOT NULL,
    roster_kind TEXT NOT NULL CHECK (roster_kind IN ('team', 'free_agent_pool', 'waiver_pool')),
    captured_at TEXT NOT NULL,
    source_observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id),
    roster_json TEXT NOT NULL,
    UNIQUE (league_season_id, platform_roster_id, captured_at)
);

CREATE TABLE roster_entity (
    roster_snapshot_id INTEGER NOT NULL REFERENCES roster_snapshot(roster_snapshot_id),
    entity_id TEXT NOT NULL REFERENCES fantasy_entity(entity_id),
    slot TEXT NOT NULL,
    roster_status TEXT NOT NULL CHECK (roster_status IN (
        'starter', 'bench', 'ir', 'taxi', 'waiver', 'free_agent', 'unknown'
    )),
    platform_entity_id TEXT,
    PRIMARY KEY (roster_snapshot_id, entity_id)
);

CREATE TABLE league_transaction (
    transaction_id INTEGER PRIMARY KEY,
    league_season_id INTEGER NOT NULL REFERENCES league_season(league_season_id),
    platform_transaction_id TEXT,
    transaction_type TEXT NOT NULL,
    transaction_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    source_observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id),
    transaction_json TEXT NOT NULL,
    UNIQUE (league_season_id, platform_transaction_id)
);

-- Features are derived, time-aware inputs to a model. Keep the feature vector
-- extensible, but require its version and cutoff so future information cannot
-- silently leak into a historical decision.
CREATE TABLE player_week_feature (
    feature_id INTEGER PRIMARY KEY,
    league_season_id INTEGER REFERENCES league_season(league_season_id),
    entity_id TEXT NOT NULL REFERENCES fantasy_entity(entity_id),
    game_id TEXT REFERENCES game(game_id),
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    as_of TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    feature_json TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    UNIQUE (league_season_id, entity_id, game_id, season, week, as_of, feature_version)
);

CREATE TABLE feature_lineage (
    feature_id INTEGER NOT NULL REFERENCES player_week_feature(feature_id),
    source_observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id),
    input_role TEXT NOT NULL,
    PRIMARY KEY (feature_id, source_observation_id, input_role)
);

-- calculated_points is the deterministic result of applying scoring_rule rows
-- to game_stat rows. platform_points is optional reconciliation evidence.
CREATE TABLE fantasy_points (
    fantasy_points_id INTEGER PRIMARY KEY,
    league_season_id INTEGER NOT NULL REFERENCES league_season(league_season_id),
    entity_id TEXT NOT NULL REFERENCES fantasy_entity(entity_id),
    game_id TEXT NOT NULL REFERENCES game(game_id),
    week INTEGER NOT NULL,
    settings_snapshot_id INTEGER NOT NULL REFERENCES league_settings_snapshot(settings_snapshot_id),
    calculated_at TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    calculated_points REAL NOT NULL,
    platform_points REAL,
    reconciliation_status TEXT NOT NULL CHECK (reconciliation_status IN (
        'pending', 'match', 'mismatch', 'not_available'
    )),
    breakdown_json TEXT NOT NULL,
    UNIQUE (league_season_id, entity_id, game_id, settings_snapshot_id, calculation_version)
);

CREATE TABLE projection (
    projection_id INTEGER PRIMARY KEY,
    league_season_id INTEGER REFERENCES league_season(league_season_id),
    entity_id TEXT NOT NULL REFERENCES fantasy_entity(entity_id),
    game_id TEXT REFERENCES game(game_id),
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    as_of TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    settings_snapshot_id INTEGER NOT NULL REFERENCES league_settings_snapshot(settings_snapshot_id),
    expected_points REAL NOT NULL,
    floor_points REAL,
    ceiling_points REAL,
    play_probability REAL CHECK (play_probability IS NULL OR (play_probability >= 0 AND play_probability <= 1)),
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    projection_json TEXT NOT NULL,
    UNIQUE (league_season_id, entity_id, game_id, season, week, as_of, model_version, feature_version)
);

CREATE TABLE analysis_run (
    analysis_run_id TEXT PRIMARY KEY,
    league_season_id INTEGER NOT NULL REFERENCES league_season(league_season_id),
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    objective TEXT NOT NULL,
    as_of TEXT NOT NULL,
    model_version TEXT NOT NULL,
    input_manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE decision (
    decision_id INTEGER PRIMARY KEY,
    analysis_run_id TEXT NOT NULL REFERENCES analysis_run(analysis_run_id),
    entity_id TEXT NOT NULL REFERENCES fantasy_entity(entity_id),
    decision_type TEXT NOT NULL CHECK (decision_type IN (
        'start', 'bench', 'add', 'drop', 'claim', 'trade', 'hold'
    )),
    target_slot TEXT,
    score REAL,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    rationale_json TEXT NOT NULL
);

-- Backtesting writes a separate row instead of mutating the original forecast.
CREATE TABLE projection_evaluation (
    evaluation_id INTEGER PRIMARY KEY,
    projection_id INTEGER NOT NULL REFERENCES projection(projection_id),
    evaluated_at TEXT NOT NULL,
    actual_points REAL,
    played INTEGER CHECK (played IS NULL OR played IN (0, 1)),
    absolute_error REAL,
    evaluation_json TEXT NOT NULL
);

CREATE INDEX source_observation_entity_idx
    ON source_observation(entity_type, entity_key, effective_at, retrieved_at);
CREATE INDEX entity_id_map_lookup_idx
    ON entity_id_map(namespace, external_id, observed_at);
CREATE INDEX game_week_idx
    ON game(season, week, kickoff_at);
CREATE INDEX game_stat_player_idx
    ON game_stat(player_entity_id, season, week);
CREATE INDEX game_stat_team_idx
    ON game_stat(team_id, season, week);
CREATE INDEX context_event_entity_idx
    ON context_event(entity_type, entity_id, effective_at, observed_at);
CREATE INDEX roster_snapshot_lookup_idx
    ON roster_snapshot(league_season_id, captured_at);
CREATE INDEX feature_lookup_idx
    ON player_week_feature(entity_id, season, week, as_of);
CREATE INDEX projection_lookup_idx
    ON projection(league_season_id, season, week, entity_id, as_of);
