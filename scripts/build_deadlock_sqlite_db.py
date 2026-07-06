#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, TextIO

DEFAULT_INPUT_DIR = Path("data/deadlock-ranked")
DEFAULT_OUTPUT_DB = Path("data/deadlock-analysis/deadlock_matches.sqlite")
DEFAULT_ASSET_MANIFEST = Path("assets/deadlock/manifest.json")
DEFAULT_ANALYSIS_MAX_MATCHES = 25_000


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def analysis_max_matches_default() -> int:
    raw_value = os.getenv("DEADLOCK_ANALYSIS_MAX_MATCHES")
    if raw_value is None or raw_value.strip() == "":
        return DEFAULT_ANALYSIS_MAX_MATCHES
    return max(0, int(raw_value))


def open_text(path: Path) -> TextIO:
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_match_files(input_dirs: list[Path], limit_files: int | None) -> list[Path]:
    patterns = (
        "deadlock_matches_*.jsonl.gz",
        "deadlock_matches_*.jsonl",
        "*.jsonl.gz",
        "*.jsonl",
    )
    files: list[Path] = []
    seen: set[Path] = set()
    for input_dir in input_dirs:
        for pattern in patterns:
            for path in sorted(input_dir.glob(pattern)):
                if path in seen:
                    continue
                seen.add(path)
                files.append(path)
    return files[:limit_files] if limit_files is not None else files


def iter_records(paths: Iterable[Path]) -> Iterable[tuple[Path, dict[str, Any]]]:
    for path in paths:
        with open_text(path) as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    yield path, value


def as_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_match(record: dict[str, Any]) -> dict[str, Any] | None:
    match = record.get("match")
    if isinstance(match, dict):
        return match
    if "match_id" in record and "players" in record:
        return record
    return None


def extract_match_id(record: dict[str, Any], match: dict[str, Any]) -> int | None:
    for value in (
        match.get("match_id"),
        record.get("match_id"),
        record.get("summary", {}).get("match_id") if isinstance(record.get("summary"), dict) else None,
    ):
        match_id = as_int(value)
        if match_id is not None:
            return match_id
    return None


def load_asset_maps(path: Path | None) -> tuple[dict[int, str], dict[int, str], dict[int, str]]:
    if path is None or not path.exists():
        return {}, {}, {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    hero_names = {
        int(hero["id"]): hero.get("name")
        for hero in manifest.get("heroes", [])
        if isinstance(hero, dict) and hero.get("id") is not None and hero.get("name")
    }
    item_names = {
        int(item["id"]): item.get("name")
        for item in manifest.get("items", [])
        if isinstance(item, dict) and item.get("id") is not None and item.get("name")
    }
    rank_names = {
        int(rank["tier"]): rank.get("name")
        for rank in manifest.get("ranks", [])
        if isinstance(rank, dict) and rank.get("tier") is not None and rank.get("name")
    }
    return hero_names, item_names, rank_names


def badge_name(badge: Any, rank_names: dict[int, str]) -> str | None:
    badge_int = as_int(badge)
    if badge_int is None:
        return None
    tier = badge_int // 10
    subtier = badge_int % 10
    name = rank_names.get(tier)
    if not name:
        return None
    return f"{name} {subtier}" if subtier else name


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = OFF;

        CREATE TABLE matches (
          match_id INTEGER PRIMARY KEY,
          collected_at TEXT,
          imported_at TEXT NOT NULL,
          input_file TEXT NOT NULL,
          start_time TEXT,
          duration_s INTEGER,
          game_mode TEXT,
          match_mode TEXT,
          winning_team TEXT,
          match_outcome TEXT,
          average_badge_team0 INTEGER,
          average_badge_team1 INTEGER,
          average_badge_team0_name TEXT,
          average_badge_team1_name TEXT,
          player_count INTEGER,
          banned_hero_ids_json TEXT,
          objectives_json TEXT,
          mid_boss_json TEXT,
          raw_json TEXT
        );

        CREATE TABLE players (
          match_id INTEGER NOT NULL,
          player_slot INTEGER NOT NULL,
          account_id INTEGER,
          team TEXT,
          assigned_lane INTEGER,
          hero_id INTEGER,
          hero_name TEXT,
          hero_build_id INTEGER,
          kills INTEGER,
          deaths INTEGER,
          assists INTEGER,
          net_worth INTEGER,
          last_hits INTEGER,
          denies INTEGER,
          player_level INTEGER,
          ability_points INTEGER,
          abandon_match_time_s INTEGER,
          final_stats_json TEXT,
          death_details_json TEXT,
          raw_json TEXT,
          PRIMARY KEY (match_id, player_slot)
        ) WITHOUT ROWID;

        CREATE TABLE player_items (
          match_id INTEGER NOT NULL,
          player_slot INTEGER NOT NULL,
          item_index INTEGER NOT NULL,
          item_id INTEGER,
          item_name TEXT,
          upgrade_id INTEGER,
          game_time_s INTEGER,
          sold_time_s INTEGER,
          net_worth_at_buy INTEGER,
          flags INTEGER,
          imbued_ability_id INTEGER,
          raw_json TEXT,
          PRIMARY KEY (match_id, player_slot, item_index)
        ) WITHOUT ROWID;

        CREATE TABLE player_stat_samples (
          match_id INTEGER NOT NULL,
          player_slot INTEGER NOT NULL,
          sample_index INTEGER NOT NULL,
          time_stamp_s INTEGER,
          kills INTEGER,
          deaths INTEGER,
          assists INTEGER,
          net_worth INTEGER,
          player_damage INTEGER,
          player_damage_taken INTEGER,
          creep_kills INTEGER,
          neutral_kills INTEGER,
          boss_damage INTEGER,
          player_healing INTEGER,
          raw_json TEXT,
          PRIMARY KEY (match_id, player_slot, sample_index)
        ) WITHOUT ROWID;

        CREATE TABLE import_runs (
          imported_at TEXT PRIMARY KEY,
          input_dirs_json TEXT NOT NULL,
          input_files INTEGER NOT NULL,
          imported_matches INTEGER NOT NULL,
          imported_players INTEGER NOT NULL,
          imported_items INTEGER NOT NULL,
          imported_stat_samples INTEGER NOT NULL
        );

        CREATE INDEX idx_matches_start_time ON matches(start_time DESC, match_id DESC);
        CREATE INDEX idx_matches_badge ON matches(average_badge_team0, average_badge_team1);
        CREATE INDEX idx_players_hero ON players(hero_id, match_id);
        CREATE INDEX idx_player_items_item ON player_items(item_id, match_id);
        """
    )


def insert_match(
    connection: sqlite3.Connection,
    input_file: Path,
    record: dict[str, Any],
    match: dict[str, Any],
    imported_at: str,
    hero_names: dict[int, str],
    item_names: dict[int, str],
    rank_names: dict[int, str],
) -> tuple[int, int, int] | None:
    match_id = extract_match_id(record, match)
    if match_id is None:
        return None

    players = match.get("players") if isinstance(match.get("players"), list) else []
    collected_at = record.get("collected_at")
    average_badge_team0 = as_int(match.get("average_badge_team0"))
    average_badge_team1 = as_int(match.get("average_badge_team1"))
    connection.execute(
        """
        INSERT OR REPLACE INTO matches (
          match_id, collected_at, imported_at, input_file, start_time, duration_s, game_mode,
          match_mode, winning_team, match_outcome, average_badge_team0, average_badge_team1,
          average_badge_team0_name, average_badge_team1_name, player_count, banned_hero_ids_json,
          objectives_json, mid_boss_json, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            match_id,
            collected_at,
            imported_at,
            str(input_file),
            match.get("start_time"),
            as_int(match.get("duration_s")),
            match.get("game_mode"),
            match.get("match_mode"),
            match.get("winning_team"),
            match.get("match_outcome"),
            average_badge_team0,
            average_badge_team1,
            badge_name(average_badge_team0, rank_names),
            badge_name(average_badge_team1, rank_names),
            len(players),
            as_json(match.get("banned_hero_ids")),
            as_json(match.get("objectives")),
            as_json(match.get("mid_boss")),
            as_json(match),
        ),
    )

    player_count = 0
    item_count = 0
    stat_count = 0
    for index, player in enumerate(players):
        if not isinstance(player, dict):
            continue
        player_slot = as_int(player.get("player_slot"))
        if player_slot is None:
            player_slot = index
        hero_id = as_int(player.get("hero_id"))
        connection.execute(
            """
            INSERT OR REPLACE INTO players (
              match_id, player_slot, account_id, team, assigned_lane, hero_id, hero_name,
              hero_build_id, kills, deaths, assists, net_worth, last_hits, denies, player_level,
              ability_points, abandon_match_time_s, final_stats_json, death_details_json, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                player_slot,
                as_int(player.get("account_id")),
                player.get("team"),
                as_int(player.get("assigned_lane")),
                hero_id,
                hero_names.get(hero_id) if hero_id is not None else None,
                as_int(player.get("hero_build_id")),
                as_int(player.get("kills")),
                as_int(player.get("deaths")),
                as_int(player.get("assists")),
                as_int(player.get("net_worth")),
                as_int(player.get("last_hits")),
                as_int(player.get("denies")),
                as_int(player.get("player_level")),
                as_int(player.get("ability_points")),
                as_int(player.get("abandon_match_time_s")),
                as_json(player.get("final_stats")),
                as_json(player.get("death_details")),
                as_json(player),
            ),
        )
        player_count += 1

        items = player.get("items") if isinstance(player.get("items"), list) else []
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item_id = as_int(item.get("item_id"))
            connection.execute(
                """
                INSERT OR REPLACE INTO player_items (
                  match_id, player_slot, item_index, item_id, item_name, upgrade_id, game_time_s,
                  sold_time_s, net_worth_at_buy, flags, imbued_ability_id, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    player_slot,
                    item_index,
                    item_id,
                    item_names.get(item_id) if item_id is not None else None,
                    as_int(item.get("upgrade_id")),
                    as_int(item.get("game_time_s")),
                    as_int(item.get("sold_time_s")),
                    as_int(item.get("net_worth_at_buy")),
                    as_int(item.get("flags")),
                    as_int(item.get("imbued_ability_id")),
                    as_json(item),
                ),
            )
            item_count += 1

        stats = player.get("stats") if isinstance(player.get("stats"), list) else []
        for sample_index, sample in enumerate(stats):
            if not isinstance(sample, dict):
                continue
            connection.execute(
                """
                INSERT OR REPLACE INTO player_stat_samples (
                  match_id, player_slot, sample_index, time_stamp_s, kills, deaths, assists, net_worth,
                  player_damage, player_damage_taken, creep_kills, neutral_kills, boss_damage,
                  player_healing, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    player_slot,
                    sample_index,
                    as_int(sample.get("time_stamp_s")),
                    as_int(sample.get("kills")),
                    as_int(sample.get("deaths")),
                    as_int(sample.get("assists")),
                    as_int(sample.get("net_worth")),
                    as_int(sample.get("player_damage")),
                    as_int(sample.get("player_damage_taken")),
                    as_int(sample.get("creep_kills")),
                    as_int(sample.get("neutral_kills")),
                    as_int(sample.get("boss_damage")),
                    as_int(sample.get("player_healing")),
                    as_json(sample),
                ),
            )
            stat_count += 1

    return player_count, item_count, stat_count


def trim_to_latest_matches(connection: sqlite3.Connection, max_matches: int) -> None:
    if max_matches <= 0:
        return
    connection.executescript(
        f"""
        CREATE TEMP TABLE keep_matches AS
        SELECT match_id
        FROM matches
        ORDER BY start_time DESC, match_id DESC
        LIMIT {int(max_matches)};

        DELETE FROM player_stat_samples WHERE match_id NOT IN (SELECT match_id FROM keep_matches);
        DELETE FROM player_items WHERE match_id NOT IN (SELECT match_id FROM keep_matches);
        DELETE FROM players WHERE match_id NOT IN (SELECT match_id FROM keep_matches);
        DELETE FROM matches WHERE match_id NOT IN (SELECT match_id FROM keep_matches);
        DROP TABLE keep_matches;
        """
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a SQLite database from Deadlock JSONL match chunks.")
    parser.add_argument("--input-dir", action="append", type=Path, default=None)
    parser.add_argument("--output-db", type=Path, default=DEFAULT_OUTPUT_DB)
    parser.add_argument("--asset-manifest", type=Path, default=DEFAULT_ASSET_MANIFEST)
    parser.add_argument("--max-matches", type=int, default=analysis_max_matches_default())
    parser.add_argument("--limit-files", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dirs = args.input_dir or [Path(os.getenv("DEADLOCK_DATA_DIR", str(DEFAULT_INPUT_DIR)))]
    files = iter_match_files(input_dirs, args.limit_files)
    imported_at = utc_iso_now()
    hero_names, item_names, rank_names = load_asset_maps(args.asset_manifest)

    args.output_db.parent.mkdir(parents=True, exist_ok=True)
    if args.output_db.exists():
        args.output_db.unlink()

    counts = {
        "matches": 0,
        "players": 0,
        "items": 0,
        "stat_samples": 0,
    }
    with sqlite3.connect(args.output_db) as connection:
        create_schema(connection)
        for input_file, record in iter_records(files):
            match = extract_match(record)
            if match is None:
                continue
            result = insert_match(connection, input_file, record, match, imported_at, hero_names, item_names, rank_names)
            if result is None:
                continue
            players, items, stat_samples = result
            counts["matches"] += 1
            counts["players"] += players
            counts["items"] += items
            counts["stat_samples"] += stat_samples
        trim_to_latest_matches(connection, args.max_matches)
        connection.execute(
            """
            INSERT INTO import_runs (
              imported_at, input_dirs_json, input_files, imported_matches, imported_players,
              imported_items, imported_stat_samples
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                imported_at,
                as_json([str(path) for path in input_dirs]),
                len(files),
                counts["matches"],
                counts["players"],
                counts["items"],
                counts["stat_samples"],
            ),
        )
        connection.commit()

    print(json.dumps({"output_db": str(args.output_db), "input_files": len(files), **counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
