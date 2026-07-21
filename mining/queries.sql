-- Read-only bootstrap queries for ~/.local/share/hippo/hippo.db.
-- Run manually; do not schedule until session ingestion freshness is proven.

-- Domain discovery by Claude project.
SELECT project_dir, COUNT(*) AS sessions
FROM claude_sessions
WHERE is_subagent = 0
GROUP BY project_dir
ORDER BY sessions DESC
LIMIT 25;

-- Subagent delegation corpus: strongest signal for reusable agent shapes.
SELECT project_dir, COUNT(*) AS delegated_runs
FROM claude_sessions
WHERE is_subagent = 1
GROUP BY project_dir
ORDER BY delegated_runs DESC
LIMIT 25;

-- Repeated command failures by repo.
SELECT git_repo, COUNT(*) AS failures
FROM events
WHERE exit_code != 0
GROUP BY git_repo
ORDER BY failures DESC
LIMIT 25;

-- Recent change outcomes for prompt gotchas and known failure modes.
SELECT content
FROM knowledge_nodes
WHERE node_type = 'change_outcome'
ORDER BY created_at DESC
LIMIT 50;
