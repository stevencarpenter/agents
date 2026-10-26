"""agent_eval.py: shared writer for agent-eval v1 records (the hippo ingest contract).

Every producer in this skill writes one JSON object per line with
``schema_version`` 1 and a ``type`` (``review_run``, ``finding``, ``verdict``,
``escape``, ``bench_run``) to its own JSONL file, then hands the whole file to
``hippo ingest agent-eval``. hippo skips ids it already holds, so the full
file is re-sent after every write. The local file is the durable copy: it is
written first, and a missing or failing hippo costs one warning line only.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCHEMA_VERSION = 1
# A wedged hippo must not hang the producer; the next write re-sends the file.
INGEST_TIMEOUT_SECONDS = 120
GIT_TIMEOUT_SECONDS = 60


def now_ms() -> int:
    """Return the current time as Unix epoch milliseconds."""
    return time.time_ns() // 1_000_000


def short_hash(text: str) -> str:
    """Return the first 16 hex characters of the SHA-256 of ``text``."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def line_hash(line: str) -> str:
    """Hash one raw source line the way hippo does.

    Normalization removes one trailing CR, then leading and trailing ASCII
    spaces and tabs only, so Python and Rust agree on every input.
    """
    return hashlib.sha256(line.removesuffix("\r").strip(" \t").encode()).hexdigest()


def rev_parse(repo: str | Path, rev: str) -> str:
    """Resolve ``rev`` in ``repo`` to a full 40-hex commit SHA.

    Raises:
        ValueError: When ``rev`` does not name a commit in ``repo``.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", "--end-of-options",
             f"{rev}^{{commit}}"],
            capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"cannot run git: {exc}") from exc
    sha = proc.stdout.strip()
    if proc.returncode != 0 or len(sha) != 40:
        raise ValueError(f"{rev!r} does not resolve to a commit in {repo}")
    return sha


def append(path: Path, records: list[dict]) -> None:
    """Append records to a JSONL file, creating it if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    torn = path.exists() and path.stat().st_size and not path.read_bytes().endswith(b"\n")
    with path.open("a", encoding="utf-8") as fh:
        if torn and records:
            fh.write("\n")  # an interrupted write must not swallow the next record
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read(path: Path) -> list[dict]:
    """Return the JSON objects in a JSONL file; unparsable lines are reported and skipped."""
    if not path.exists():
        return []
    records = []
    # One record per `\n`: json.dumps(ensure_ascii=False) leaves U+2028 unescaped.
    for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            print(f"warning: {path}:{number} is not JSON; skipped", file=sys.stderr)
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def ingest(path: Path) -> None:
    """Send ``path`` to ``hippo ingest agent-eval``; never fail the caller.

    A missing binary, a non-zero exit, or a timeout prints exactly one warning
    line to stderr. The records stay in ``path`` and the next ingest sends them.
    """
    hippo = shutil.which("hippo")
    if hippo is None:
        print(f"warning: hippo not on PATH; {path} not ingested", file=sys.stderr)
        return
    try:
        proc = subprocess.run(
            [hippo, "ingest", "agent-eval", str(path)],
            capture_output=True, text=True, errors="replace", check=False,
            timeout=INGEST_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        reason = type(exc).__name__
    else:
        if proc.returncode == 0:
            print(f"hippo: {proc.stdout.strip()}")
            return
        last = (proc.stderr.strip().splitlines() or ["no output"])[-1]
        reason = f"exit {proc.returncode}: {last}"
    print(f"warning: hippo ingest agent-eval failed ({reason}); records kept in {path}", file=sys.stderr)
