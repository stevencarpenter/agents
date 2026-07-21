# Spec: `checkpoint.py` — resumable job checkpoint store

A small library module used by batch jobs to record progress and resume after a crash.

## Behavior

- `CheckpointStore(directory)` — stores one JSON file per job under `directory`
  (created if missing).
- `save(job_id, state)` — atomically persist a mapping of job state. Partial writes
  must never be observable: a crash mid-save leaves the previous checkpoint intact.
- `load(job_id)` — return the saved state. A missing checkpoint is an expected
  condition the caller handles; a corrupt (unparseable) checkpoint file is a bug
  and must raise something distinguishable from "missing".
- `delete(job_id)` — remove the checkpoint; deleting a missing checkpoint is a no-op.
- `job_id` may only contain `[a-zA-Z0-9_-]`; anything else must be rejected before
  touching the filesystem (path traversal like `../../etc/passwd` must be impossible).

## Constraints

- Standard library only.
- Typed public signatures throughout.
- Ship tests alongside in `test_checkpoint.py` covering: round-trip, atomicity
  strategy (at minimum: temp-file-then-rename is used), missing vs corrupt
  distinction, job_id validation, and delete idempotency.
