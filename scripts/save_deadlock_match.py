#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("data/deadlock-analysis/deadlock_matches.sqlite")
DEFAULT_OUTPUT = Path("data/deadlock-saved/saved_matches.jsonl")


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_existing_records(path: Path) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            match_id = extract_match_id(record)
            if match_id is not None:
                records[match_id] = record
    return records


def extract_match_id(record: dict[str, Any]) -> int | None:
    for value in (
        record.get("match_id"),
        record.get("summary", {}).get("match_id") if isinstance(record.get("summary"), dict) else None,
        record.get("match", {}).get("match_id") if isinstance(record.get("match"), dict) else None,
    ):
        match_id = as_int(value)
        if match_id is not None:
            return match_id
    return None


def summarize_match(match: dict[str, Any]) -> dict[str, Any]:
    players = match.get("players") if isinstance(match.get("players"), list) else []
    return {
        "match_id": match.get("match_id"),
        "start_time": match.get("start_time"),
        "duration_s": match.get("duration_s"),
        "game_mode": match.get("game_mode"),
        "match_mode": match.get("match_mode"),
        "winning_team": match.get("winning_team"),
        "match_outcome": match.get("match_outcome"),
        "average_badge_team0": match.get("average_badge_team0"),
        "average_badge_team1": match.get("average_badge_team1"),
        "player_count": len(players),
        "hero_ids": [player.get("hero_id") for player in players if isinstance(player, dict)],
    }


def saved_record(match: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "collected_at": utc_iso_now(),
        "source": {
            "name": "deadlock-gg-local-save",
            "endpoint": "sqlite:matches.raw_json",
        },
        "summary": summarize_match(match),
        "match": match,
    }


def load_match_from_db(db_path: Path, match_id: int) -> dict[str, Any] | None:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT raw_json FROM matches WHERE match_id = ?", (match_id,)).fetchone()
    if row is None or row[0] is None:
        return None
    value = json.loads(row[0])
    return value if isinstance(value, dict) else None


def write_records(path: Path, records: dict[int, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for match_id in sorted(records, reverse=True):
            handle.write(json.dumps(records[match_id], separators=(",", ":"), sort_keys=True))
            handle.write("\n")
    tmp_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save Deadlock matches so --fresh pulls keep them in the analysis DB.")
    parser.add_argument("match_ids", nargs="+", type=int, help="Match id(s) to save from the current SQLite DB.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.db.exists():
        raise SystemExit(f"SQLite DB not found: {args.db}")

    records = load_existing_records(args.output)
    saved = 0
    missing: list[int] = []
    for match_id in args.match_ids:
        match = load_match_from_db(args.db, match_id)
        if match is None:
            missing.append(match_id)
            continue
        records[match_id] = saved_record(match)
        saved += 1

    write_records(args.output, records)
    print(f"saved={saved} total_saved={len(records)} output={args.output}")
    if missing:
        print("missing=" + ",".join(str(match_id) for match_id in missing))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
