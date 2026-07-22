from __future__ import annotations

# The registry's source-of-truth `model:` value uses Claude Code's own alias
# vocabulary (`inherit`, `haiku`, `sonnet`, `opus`, `fable`) because that's the
# native format agents are authored in. Other targets don't share that
# vocabulary, so each needs its own mapping to a real, current model id.
#
# `inherit` never appears in these tables: every emitter treats it as "omit
# the model field" so the agent inherits whatever model the parent session is
# already running, matching each target's own documented default behavior.
#
# Keep this table to ids actually verified against each target's current
# model catalog at the time they're added — do not guess a plausible-looking
# id. Revisit when a target's catalog changes.
_TARGET_MODEL_IDS: dict[str, dict[str, str]] = {
    "codex": {
        # Codex documents Terra as the efficient tier for exploration,
        # read-heavy scans, and supporting-document work.
        "haiku": "gpt-5.6-terra",
    },
    "opencode": {
        # OpenCode has no built-in cost-tier alias; the provider/model-id pair
        # is the only supported format, so this hardcodes a specific model.
        "haiku": "anthropic/claude-haiku-4-5",
    },
    "cursor": {
        "haiku": "claude-haiku-4-5",
    },
}


def translate_model(claude_model: str, target: str) -> str | None:
    """Map a Claude-alias `model:` value to the equivalent id for another target.

    Args:
        claude_model: The registry source's `model` metadata value (e.g.
            ``"haiku"``, ``"inherit"``, or empty/unset).
        target: One of ``"codex"``, ``"opencode"``, ``"cursor"``.

    Returns:
        The target-specific model id to emit, or ``None`` when the field
        should be omitted (unset, ``inherit``, or a value this table doesn't
        know how to translate — an unrecognized value is passed through
        as-is only for Claude Code itself, never fabricated for another
        target).
    """
    if not claude_model or claude_model == "inherit":
        return None
    return _TARGET_MODEL_IDS.get(target, {}).get(claude_model)
