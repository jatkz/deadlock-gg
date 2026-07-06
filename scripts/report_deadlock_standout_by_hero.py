#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("data/deadlock-analysis/deadlock_matches.sqlite")


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def mmss(seconds: int | float | None) -> str:
    if seconds is None:
        return "-"
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}:{secs:02d}"


def performance_score(row: sqlite3.Row) -> float:
    final_stats = json_loads(row["final_stats_json"])
    kills = as_int(row["kills"])
    deaths = as_int(row["deaths"])
    assists = as_int(row["assists"])
    net_worth = as_int(row["net_worth"])
    player_damage = as_int(final_stats.get("player_damage"))
    boss_damage = as_int(final_stats.get("boss_damage"))
    healing = as_int(final_stats.get("player_healing"))
    denied = as_int(final_stats.get("denies"))
    creep_kills = as_int(final_stats.get("creep_kills"), as_int(row["last_hits"]))
    won_bonus = 4 if row["won"] else 0
    return (
        kills * 6.0
        + assists * 2.5
        - deaths * 1.5
        + net_worth / 1000.0
        + player_damage / 1200.0
        + boss_damage / 1000.0
        + healing / 1500.0
        + creep_kills / 45.0
        + denied / 20.0
        + won_bonus
    )


def load_player_rows(connection: sqlite3.Connection, min_duration_s: int | None, max_duration_s: int | None) -> list[dict[str, Any]]:
    clauses = []
    values: list[Any] = []
    if min_duration_s is not None:
        clauses.append("m.duration_s >= ?")
        values.append(min_duration_s)
    if max_duration_s is not None:
        clauses.append("m.duration_s <= ?")
        values.append(max_duration_s)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    query = f"""
        SELECT
          p.match_id, p.player_slot, p.hero_id, p.hero_name, p.kills, p.deaths,
          p.assists, p.net_worth, p.last_hits, p.final_stats_json,
          m.duration_s,
          CASE WHEN m.winning_team = p.team THEN 1 ELSE 0 END AS won
        FROM players p
        JOIN matches m USING(match_id)
        {where}
    """
    rows = []
    for row in connection.execute(query, values):
        value = dict(row)
        value["score"] = performance_score(row)
        rows.append(value)
    return rows


def format_percent(value: float) -> str:
    if value.is_integer():
        return f"{int(value)}%"
    return f"{value:g}%"


def print_report(rows: list[dict[str, Any]], top_percent: float, min_games: int) -> None:
    if not rows:
        print("No player rows found for the selected filters.")
        return

    rows.sort(key=lambda row: row["score"], reverse=True)
    top_count = max(1, round(len(rows) * top_percent / 100))
    standout_rows = rows[:top_count]

    overall_counts: dict[tuple[int, str], int] = defaultdict(int)
    standout_counts: dict[tuple[int, str], int] = defaultdict(int)
    standout_scores: dict[tuple[int, str], list[float]] = defaultdict(list)
    standout_durations: dict[tuple[int, str], list[int]] = defaultdict(list)
    standout_wins: dict[tuple[int, str], int] = defaultdict(int)

    for row in rows:
        key = (as_int(row["hero_id"]), row["hero_name"] or f"Hero {row['hero_id']}")
        overall_counts[key] += 1
    for row in standout_rows:
        key = (as_int(row["hero_id"]), row["hero_name"] or f"Hero {row['hero_id']}")
        standout_counts[key] += 1
        standout_scores[key].append(float(row["score"]))
        standout_durations[key].append(as_int(row["duration_s"]))
        standout_wins[key] += as_int(row["won"])

    total_players = len(rows)
    total_standouts = len(standout_rows)
    print("Standout Performance Distribution By Hero")
    print(f"players: {total_players}")
    print(f"standouts: {total_standouts} (top {format_percent(top_percent)})")
    print()
    print(
        f"{'Hero':<18} {'Standout':>8} {'All':>6} {'SO Share':>8} "
        f"{'All Share':>9} {'Lift':>6} {'Avg Score':>9} {'Avg Dur':>8} {'Win%':>6}"
    )
    print("-" * 86)

    ranked = sorted(
        (
            {
                "hero": key[1],
                "standout": standout_counts[key],
                "overall": overall_counts[key],
                "standout_share": standout_counts[key] / total_standouts,
                "overall_share": overall_counts[key] / total_players,
                "lift": (standout_counts[key] / total_standouts) / (overall_counts[key] / total_players),
                "avg_score": sum(standout_scores[key]) / len(standout_scores[key]),
                "avg_duration": sum(standout_durations[key]) / len(standout_durations[key]),
                "win_rate": standout_wins[key] / standout_counts[key],
            }
            for key in standout_counts
            if standout_counts[key] >= min_games
        ),
        key=lambda item: (item["standout"], item["lift"], item["avg_score"]),
        reverse=True,
    )

    for item in ranked:
        print(
            f"{item['hero'][:18]:<18} {item['standout']:>8d} {item['overall']:>6d} "
            f"{item['standout_share'] * 100:>7.1f}% {item['overall_share'] * 100:>8.1f}% "
            f"{item['lift']:>6.2f} {item['avg_score']:>9.1f} {mmss(item['avg_duration']):>8} "
            f"{item['win_rate'] * 100:>5.1f}%"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report standout Deadlock performance distribution by hero.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--top-percent", type=float, default=5.0)
    parser.add_argument("--min-games", type=int, default=1)
    parser.add_argument("--min-duration-minutes", type=float)
    parser.add_argument("--max-duration-minutes", type=float)
    return parser.parse_args()


def minutes_to_seconds(value: float | None) -> int | None:
    if value is None:
        return None
    return max(0, round(value * 60))


def main() -> int:
    args = parse_args()
    if not args.db.exists():
        raise SystemExit(f"SQLite database not found: {args.db}")
    if args.top_percent <= 0 or args.top_percent > 100:
        raise SystemExit("--top-percent must be > 0 and <= 100")

    with sqlite3.connect(args.db) as connection:
        connection.row_factory = sqlite3.Row
        rows = load_player_rows(
            connection,
            minutes_to_seconds(args.min_duration_minutes),
            minutes_to_seconds(args.max_duration_minutes),
        )
    print_report(rows, args.top_percent, max(1, args.min_games))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
