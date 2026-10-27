"""
ingest/load_signals.py  —  Week 1 ingestion + validation.

Takes a JSON file of raw signal dicts and runs each through the Signal schema.
Valid signals pass; malformed ones are collected with their error, never silently
dropped. This is the "reject bad data at the door" layer — the foundation the
agent, extraction, and scorer will all sit on later.

Usage:
    python -m ingest.load_signals data/samples/sample_signals.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# allow running from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402
from schema.signal import Signal  # noqa: E402


def load_raw(path: str) -> list[dict]:
    """Load the raw JSON array. No validation yet — just read the file."""
    with open(path) as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array of signal objects")
    return data


def validate_signals(raw: list[dict]) -> tuple[list[Signal], list[dict]]:
    """
    Split raw records into (valid Signal objects, rejected records-with-errors).
    Nothing is silently dropped: every rejection carries the reason.
    """
    valid: list[Signal] = []
    rejected: list[dict] = []
    for i, record in enumerate(raw):
        try:
            valid.append(Signal(**record))
        except ValidationError as e:
            rejected.append({
                "index": i,
                "record_id": record.get("signal_id", "<no-id>"),
                "errors": [f"{err['loc']}: {err['msg']}" for err in e.errors()],
            })
    return valid, rejected


def summarize(valid: list[Signal], rejected: list[dict]) -> None:
    """Human-readable report of what got in and what didn't."""
    print("INGESTION SUMMARY")
    print("=" * 50)
    print(f"Valid signals:    {len(valid)}")
    print(f"Rejected records: {len(rejected)}")
    print()

    if valid:
        print("Accepted:")
        for s in valid:
            mark = "validated" if s.is_validated else "UNVALIDATED (won't score)"
            print(f"  - {s.company_id} / {s.signal_type.value} / {s.signal_value}  [{mark}]")
        print()

    if rejected:
        print("Rejected (with reason):")
        for r in rejected:
            print(f"  - record {r['index']} ({r['record_id']}):")
            for err in r["errors"]:
                print(f"      ! {err}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m ingest.load_signals <signals.json>", file=sys.stderr)
        return 2
    raw = load_raw(sys.argv[1])
    valid, rejected = validate_signals(raw)
    summarize(valid, rejected)
    # exit non-zero if everything was rejected — useful for CI later
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
