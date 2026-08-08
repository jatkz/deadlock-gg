#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("data/deadlock-analysis/deadlock_matches.sqlite")
DEFAULT_ASSET_MANIFEST = Path("assets/deadlock/manifest.json")


@dataclass(frozen=True)
class PlayerContext:
    match_id: int
    player_slot: int
    hero_id: int | None
    hero_name: str
    team: str
    assigned_lane: int | None
    won: bool


@dataclass
class ItemStats:
    item_id: int
    item_name: str
    buyers: int = 0
    wins: int = 0
    first_buy_times: list[int] | None = None


def as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def minutes_to_seconds(value: float | None) -> int | None:
    if value is None:
        return None
    return max(0, round(value * 60))


def mmss(seconds: int | float | None) -> str:
    if seconds is None:
        return "-"
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}:{secs:02d}"


def pct(value: float) -> str:
    return f"{value * 100:5.1f}%"


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def matches_token(value: Any, token: str) -> bool:
    if not token:
        return True
    return token in normalized(value)


def wilson_interval(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p = wins / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def load_item_assets(path: Path) -> dict[int, dict[str, Any]]:
    if not path.exists():
        return {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return {
        int(item["id"]): item
        for item in manifest.get("items", [])
        if isinstance(item, dict) and item.get("id") is not None
    }


def load_players(
    connection: sqlite3.Connection,
    min_duration_s: int | None,
    max_duration_s: int | None,
) -> list[PlayerContext]:
    clauses = []
    values: list[Any] = []
    if min_duration_s is not None:
        clauses.append("m.duration_s >= ?")
        values.append(min_duration_s)
    if max_duration_s is not None:
        clauses.append("m.duration_s <= ?")
        values.append(max_duration_s)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = connection.execute(
        f"""
        SELECT
          p.match_id, p.player_slot, p.hero_id, p.hero_name, p.team, p.assigned_lane,
          CASE WHEN m.winning_team = p.team THEN 1 ELSE 0 END AS won
        FROM players p
        JOIN matches m USING(match_id)
        {where}
        """,
        values,
    )
    return [
        PlayerContext(
            match_id=int(row["match_id"]),
            player_slot=int(row["player_slot"]),
            hero_id=as_int(row["hero_id"]),
            hero_name=row["hero_name"] or f"Hero {row['hero_id']}",
            team=row["team"] or "",
            assigned_lane=as_int(row["assigned_lane"]),
            won=bool(row["won"]),
        )
        for row in rows
    ]


def context_has_enemy(
    player: PlayerContext,
    match_players: dict[int, list[PlayerContext]],
    enemy_token: str,
    enemy_scope: str,
) -> bool:
    if not enemy_token:
        return True
    for enemy in match_players.get(player.match_id, []):
        if enemy.team == player.team:
            continue
        if enemy_scope == "lane" and enemy.assigned_lane != player.assigned_lane:
            continue
        if matches_token(enemy.hero_name, enemy_token) or str(enemy.hero_id or "") == enemy_token:
            return True
    return False


def load_first_item_buys(
    connection: sqlite3.Connection,
    context_keys: set[tuple[int, int]],
    item_assets: dict[int, dict[str, Any]],
    include_abilities: bool,
    before_s: int | None,
    item_token: str,
) -> dict[tuple[int, int], dict[int, tuple[str, int]]]:
    if not context_keys:
        return {}
    buys_by_player: dict[tuple[int, int], dict[int, tuple[str, int]]] = {key: {} for key in context_keys}
    for row in connection.execute(
        """
        SELECT match_id, player_slot, item_id, item_name, game_time_s
        FROM player_items
        WHERE item_id IS NOT NULL
          AND game_time_s IS NOT NULL
        ORDER BY match_id, player_slot, item_id, game_time_s
        """
    ):
        key = (int(row["match_id"]), int(row["player_slot"]))
        if key not in context_keys:
            continue
        item_id = int(row["item_id"])
        asset = item_assets.get(item_id, {})
        item_type = normalized(asset.get("type"))
        if item_type == "ability" and not include_abilities:
            continue
        item_name = asset.get("name") or row["item_name"] or f"Item {item_id}"
        if item_token and not (matches_token(item_name, item_token) or str(item_id) == item_token):
            continue
        buy_time_s = as_int(row["game_time_s"])
        if buy_time_s is None:
            continue
        if before_s is not None and buy_time_s > before_s:
            continue
        current = buys_by_player[key].get(item_id)
        if current is None or buy_time_s < current[1]:
            buys_by_player[key][item_id] = (str(item_name), buy_time_s)
    return buys_by_player


def print_report(
    context_players: list[PlayerContext],
    buys_by_player: dict[tuple[int, int], dict[int, tuple[str, int]]],
    args: argparse.Namespace,
) -> None:
    if not context_players:
        print("No matching player contexts found.")
        return

    baseline_wins = sum(1 for player in context_players if player.won)
    baseline_rate = baseline_wins / len(context_players)
    stats_by_item: dict[int, ItemStats] = {}

    for player in context_players:
        key = (player.match_id, player.player_slot)
        for item_id, (item_name, buy_time_s) in buys_by_player.get(key, {}).items():
            stats = stats_by_item.setdefault(item_id, ItemStats(item_id=item_id, item_name=item_name, first_buy_times=[]))
            stats.buyers += 1
            stats.wins += 1 if player.won else 0
            assert stats.first_buy_times is not None
            stats.first_buy_times.append(buy_time_s)

    ranked = []
    for stats in stats_by_item.values():
        if stats.buyers < args.min_matches:
            continue
        assert stats.first_buy_times is not None
        win_rate = stats.wins / stats.buyers
        low, high = wilson_interval(stats.wins, stats.buyers)
        avg_buy_s = sum(stats.first_buy_times) / len(stats.first_buy_times)
        ranked.append(
            {
                "item": stats,
                "win_rate": win_rate,
                "pick_rate": stats.buyers / len(context_players),
                "lift": win_rate - baseline_rate,
                "wilson_low": low,
                "wilson_high": high,
                "avg_buy_s": avg_buy_s,
            }
        )

    ranked.sort(key=lambda item: (item["lift"], item["win_rate"], item["item"].buyers), reverse=True)
    ranked = ranked[: args.limit]

    hero = args.hero or "any hero"
    enemy = args.enemy or "any enemy"
    before = f" by {mmss(minutes_to_seconds(args.before_minutes))}" if args.before_minutes is not None else ""
    print("Deadlock Item Matchup Win Rates")
    print(f"context: {hero} vs {enemy} ({args.enemy_scope} scope){before}")
    print(f"players: {len(context_players)}")
    print(f"baseline: {baseline_wins}/{len(context_players)} wins ({pct(baseline_rate).strip()})")
    print(f"min matches: {args.min_matches}")
    print()
    print(f"{'Item':<28} {'Buyers':>6} {'Pick%':>7} {'Win%':>7} {'Lift':>7} {'Wilson 95%':>17} {'Avg Buy':>8}")
    print("-" * 92)
    for item in ranked:
        stats = item["item"]
        interval = f"{pct(item['wilson_low']).strip()}-{pct(item['wilson_high']).strip()}"
        print(
            f"{stats.item_name[:28]:<28} {stats.buyers:>6d} {pct(item['pick_rate']):>7} "
            f"{pct(item['win_rate']):>7} {item['lift'] * 100:>+6.1f}% {interval:>17} {mmss(item['avg_buy_s']):>8}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report item win rates for hero/enemy contexts from local Deadlock SQLite data.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--asset-manifest", type=Path, default=DEFAULT_ASSET_MANIFEST)
    parser.add_argument("--hero", help="Hero name or hero ID for the buyer, for example Wraith or 7.")
    parser.add_argument("--enemy", help="Enemy hero name or hero ID to match against.")
    parser.add_argument("--enemy-scope", choices=("team", "lane"), default="team", help="Match enemy anywhere on the opposing team or only same lane.")
    parser.add_argument("--item", help="Optional item name or item ID filter.")
    parser.add_argument("--before-minutes", type=float, default=12.0, help="Only count items first bought by this game minute. Omit with --no-before.")
    parser.add_argument("--no-before", action="store_true", help="Count item purchases at any time.")
    parser.add_argument("--min-duration-minutes", type=float)
    parser.add_argument("--max-duration-minutes", type=float)
    parser.add_argument("--min-matches", type=int, default=20)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--include-abilities", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.db.exists():
        raise SystemExit(f"SQLite database not found: {args.db}")

    hero_token = normalized(args.hero)
    enemy_token = normalized(args.enemy)
    item_token = normalized(args.item)
    before_s = None if args.no_before else minutes_to_seconds(args.before_minutes)
    min_duration_s = minutes_to_seconds(args.min_duration_minutes)
    max_duration_s = minutes_to_seconds(args.max_duration_minutes)
    item_assets = load_item_assets(args.asset_manifest)

    with sqlite3.connect(args.db) as connection:
        connection.row_factory = sqlite3.Row
        players = load_players(connection, min_duration_s, max_duration_s)
        match_players: dict[int, list[PlayerContext]] = {}
        for player in players:
            match_players.setdefault(player.match_id, []).append(player)

        context_players = [
            player
            for player in players
            if (not hero_token or matches_token(player.hero_name, hero_token) or str(player.hero_id or "") == hero_token)
            and context_has_enemy(player, match_players, enemy_token, args.enemy_scope)
        ]
        context_keys = {(player.match_id, player.player_slot) for player in context_players}
        buys_by_player = load_first_item_buys(
            connection,
            context_keys,
            item_assets,
            args.include_abilities,
            before_s,
            item_token,
        )

    print_report(context_players, buys_by_player, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
