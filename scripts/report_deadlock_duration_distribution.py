#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
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


def percentile(sorted_values: list[int], percent: int) -> int | None:
    if not sorted_values:
        return None
    index = round((percent / 100) * (len(sorted_values) - 1))
    return sorted_values[index]


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


def print_distribution(durations: list[int]) -> None:
    if not durations:
        print("No matches found.")
        return

    sorted_durations = sorted(durations)
    total = len(sorted_durations)
    average = sum(sorted_durations) / total
    median = percentile(sorted_durations, 50)
    print("Match Duration Distribution")
    print(f"matches: {total}")
    print(f"min: {mmss(sorted_durations[0])}")
    print(f"avg: {mmss(average)}")
    print(f"median: {mmss(median)}")
    print(f"max: {mmss(sorted_durations[-1])}")
    print()

    buckets = [
        (0, 720, "<12 min"),
        (720, 900, "12-15 min"),
        (900, 1200, "15-20 min"),
        (1200, 1500, "20-25 min"),
        (1500, 1800, "25-30 min"),
        (1800, 2100, "30-35 min"),
        (2100, 2400, "35-40 min"),
        (2400, 2700, "40-45 min"),
        (2700, 3000, "45-50 min"),
        (3000, 3600, "50-60 min"),
        (3600, 999999, "60+ min"),
    ]
    print("Buckets")
    for lower, upper, label in buckets:
        count = sum(1 for duration in sorted_durations if lower <= duration < upper)
        print(f"{label:>9}: {count:4d} {count * 100 / total:5.1f}%")
    print()

    print("Percentiles")
    for percent in (5, 10, 25, 50, 75, 90, 95, 99):
        print(f"P{percent:<2}: {mmss(percentile(sorted_durations, percent))}")


def print_top_performance_comparison(connection: sqlite3.Connection, top_percent: float) -> None:
    query = """
        SELECT
          p.kills, p.deaths, p.assists, p.net_worth, p.last_hits, p.final_stats_json,
          m.duration_s,
          CASE WHEN m.winning_team = p.team THEN 1 ELSE 0 END AS won
        FROM players p
        JOIN matches m USING(match_id)
    """
    scored = []
    for row in connection.execute(query):
        duration = as_int(row["duration_s"])
        scored.append((performance_score(row), duration))

    if not scored:
        return

    scored.sort(key=lambda item: item[0], reverse=True)
    top_count = max(1, round(len(scored) * top_percent / 100))
    groups = [
        ("top " + format_percent(top_percent), [duration for _score, duration in scored[:top_count]]),
        ("all players", [duration for _score, duration in scored]),
    ]
    print()
    print("Performance Duration Comparison")
    for label, durations in groups:
        sorted_durations = sorted(durations)
        average = sum(sorted_durations) / len(sorted_durations)
        print(
            f"{label:>11}: n={len(sorted_durations):5d} "
            f"avg={mmss(average):>5} median={mmss(percentile(sorted_durations, 50)):>5} "
            f"P25={mmss(percentile(sorted_durations, 25)):>5} P75={mmss(percentile(sorted_durations, 75)):>5}"
        )


def format_percent(value: float) -> str:
    if value.is_integer():
        return f"{int(value)}%"
    return f"{value:g}%"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report Deadlock match duration distribution from SQLite.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--top-performance-percent",
        type=float,
        default=5.0,
        help="Compare duration of top scored player performances. Use 0 to disable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.db.exists():
        raise SystemExit(f"SQLite database not found: {args.db}")

    with sqlite3.connect(args.db) as connection:
        connection.row_factory = sqlite3.Row
        durations = [
            as_int(row["duration_s"])
            for row in connection.execute("SELECT duration_s FROM matches WHERE duration_s IS NOT NULL")
        ]
        print_distribution(durations)
        if args.top_performance_percent > 0:
            print_top_performance_comparison(connection, args.top_performance_percent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
