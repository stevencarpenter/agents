from __future__ import annotations

# Only ids verified against each target's current catalog; do not guess one.
# `inherit` is never mapped: every emitter omits the field so the parent model applies.
_TARGET_MODEL_IDS: dict[str, dict[str, str]] = {
    "codex": {
        # Codex documents Terra as the efficient tier for exploration,
        # read-heavy scans, and supporting-document work.
        "haiku": "gpt-5.6-terra",
    },
    "opencode": {
        # OpenCode has no built-in cost-tier alias; the provider/model-id pair
        # is the only supported format, so this hardcodes a specific model.
        "haiku": "anthropic/claude-haiku-5-5",
    },
    "cursor": {
        # Cursor lists Haiku only with an effort suffix; medium without thinking.
        "haiku": "claude-haiku-5-5-medium",
    },
}


def translate_model(claude_model: str, target: str) -> str | None:
    """Return the target's id for a Claude alias, or None to omit the field."""
    return _TARGET_MODEL_IDS.get(target, {}).get(claude_model)
