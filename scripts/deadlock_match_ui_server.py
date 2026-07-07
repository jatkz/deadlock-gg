#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import sqlite3
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

DEFAULT_DB = Path("data/deadlock-analysis/deadlock_matches.sqlite")
DEFAULT_ASSET_MANIFEST = Path("assets/deadlock/manifest.json")
DEFAULT_STATIC_DIR = Path("ui")


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def optional_int(value: Any, minimum: int = 0) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    parsed = as_int(value, -1)
    if parsed < minimum:
        return None
    return parsed


def optional_float(value: Any, minimum: float = 0.0) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    parsed = as_float(value, -1.0)
    if parsed < minimum:
        return None
    return parsed


def json_loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def mmss(seconds: int | None) -> str:
    if seconds is None:
        return ""
    minutes, secs = divmod(max(0, seconds), 60)
    return f"{minutes}:{secs:02d}"


def estimate_net_worth_at(samples: list[dict[str, Any]], event_time_s: int | None) -> dict[str, Any] | None:
    if event_time_s is None or not samples:
        return None
    candidates = []
    for sample in samples:
        sample_time_s = optional_int(sample.get("time_stamp_s"))
        net_worth = optional_int(sample.get("net_worth"))
        if sample_time_s is None or net_worth is None:
            continue
        candidates.append((abs(sample_time_s - event_time_s), sample_time_s, net_worth))
    if not candidates:
        return None

    _distance, sample_time_s, net_worth = min(candidates, key=lambda item: (item[0], item[1]))
    if sample_time_s == event_time_s:
        timing = "at"
    elif sample_time_s < event_time_s:
        timing = "before"
    else:
        timing = "after"
    return {
        "value": net_worth,
        "timeS": sample_time_s,
        "timeText": mmss(sample_time_s),
        "timing": timing,
        "deltaS": abs(sample_time_s - event_time_s),
        "source": "player_stat_samples",
    }


def performance_score(row: dict[str, Any]) -> float:
    final_stats = json_loads(row.get("final_stats_json")) or {}
    kills = as_int(row.get("kills"))
    deaths = as_int(row.get("deaths"))
    assists = as_int(row.get("assists"))
    net_worth = as_int(row.get("net_worth"))
    player_damage = as_int(final_stats.get("player_damage"))
    boss_damage = as_int(final_stats.get("boss_damage"))
    healing = as_int(final_stats.get("player_healing"))
    denied = as_int(final_stats.get("denies"))
    creep_kills = as_int(final_stats.get("creep_kills"), as_int(row.get("last_hits")))
    won_bonus = 4 if row.get("won") else 0

    return round(
        kills * 6.0
        + assists * 2.5
        - deaths * 1.5
        + net_worth / 1000.0
        + player_damage / 1200.0
        + boss_damage / 1000.0
        + healing / 1500.0
        + creep_kills / 45.0
        + denied / 20.0
        + won_bonus,
        2,
    )


def final_stats_for(row: dict[str, Any]) -> dict[str, Any]:
    if isinstance(row.get("finalStats"), dict):
        return row["finalStats"]
    return json_loads(row.get("final_stats_json")) or {}


def death_details_for(row: dict[str, Any]) -> list[dict[str, Any]]:
    value = json_loads(row.get("death_details_json"))
    if value is None:
        raw_player = json_loads(row.get("raw_json")) or {}
        value = raw_player.get("death_details")
    if not isinstance(value, list):
        return []
    details = [item for item in value if isinstance(item, dict)]
    details.sort(key=lambda item: as_int(item.get("game_time_s")))
    return details


def kda_ratio(row: dict[str, Any]) -> float:
    kills = as_int(row.get("kills"))
    assists = as_int(row.get("assists"))
    deaths = max(1, as_int(row.get("deaths")))
    return round((kills + assists) / deaths, 2)


def performance_reasons(row: dict[str, Any]) -> list[str]:
    final_stats = final_stats_for(row)
    kills = as_int(row.get("kills"))
    deaths = as_int(row.get("deaths"))
    assists = as_int(row.get("assists"))
    net_worth = as_int(row.get("net_worth"))
    player_damage = as_int(final_stats.get("player_damage"))
    boss_damage = as_int(final_stats.get("boss_damage"))
    healing = as_int(final_stats.get("player_healing"))
    creep_kills = as_int(final_stats.get("creep_kills"), as_int(row.get("last_hits")))

    candidates = [
        ("KDA spike", kills * 6.0 + assists * 2.5 - deaths * 1.5),
        ("high damage", player_damage / 1200.0),
        ("high net worth", net_worth / 1000.0),
        ("healing output", healing / 1500.0),
        ("boss damage", boss_damage / 1000.0),
        ("farm lead", creep_kills / 45.0),
    ]
    if row.get("won"):
        candidates.append(("won match", 4.0))
    candidates = [(label, score) for label, score in candidates if score > 0]
    candidates.sort(key=lambda item: item[1], reverse=True)
    return [label for label, _score in candidates[:3]]


def dict_rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def asset_payload(asset_id: int, assets: dict[int, dict[str, Any]], fallback_prefix: str) -> dict[str, str | int]:
    asset = assets.get(asset_id, {})
    return {
        "id": asset_id,
        "name": asset.get("name") or f"{fallback_prefix} {asset_id}",
        "image": asset.get("image") or "",
        "type": asset.get("type") or "",
    }


@dataclass
class AppState:
    db_path: Path
    static_dir: Path
    hero_assets: dict[int, dict[str, Any]]
    item_assets: dict[int, dict[str, Any]]
    score_percentiles: dict[tuple[int, int], float]
    score_count: int


def load_assets(path: Path) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    if not path.exists():
        return {}, {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    heroes = {
        int(hero["id"]): {
            "name": hero.get("name") or str(hero["id"]),
            "icon": hero.get("icon") or "",
            "card": hero.get("card") or hero.get("icon") or "",
        }
        for hero in manifest.get("heroes", [])
        if isinstance(hero, dict) and hero.get("id") is not None
    }
    items = {
        int(item["id"]): {
            "name": item.get("name") or str(item["id"]),
            "image": item.get("image") or "",
            "type": item.get("type") or "",
            "slot": item.get("item_slot_type") or "",
            "tier": str(item.get("item_tier") or ""),
            "cost": item.get("cost"),
        }
        for item in manifest.get("items", [])
        if isinstance(item, dict) and item.get("id") is not None
    }
    return heroes, items


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def build_score_percentiles(db_path: Path) -> tuple[dict[tuple[int, int], float], int]:
    if not db_path.exists():
        return {}, 0
    query = """
        SELECT
          p.match_id, p.player_slot, p.kills, p.deaths, p.assists, p.net_worth,
          p.last_hits, p.final_stats_json,
          CASE WHEN m.winning_team = p.team THEN 1 ELSE 0 END AS won
        FROM players p
        JOIN matches m USING(match_id)
    """
    with connect(db_path) as connection:
        rows = [dict(row) for row in connection.execute(query)]

    scored = [
        ((as_int(row["match_id"]), as_int(row["player_slot"])), performance_score(row))
        for row in rows
    ]
    scored.sort(key=lambda item: item[1])
    count = len(scored)
    if count <= 1:
        return {key: 100.0 for key, _score in scored}, count
    return {key: round(index * 100.0 / (count - 1), 1) for index, (key, _score) in enumerate(scored)}, count


class DeadlockUiHandler(SimpleHTTPRequestHandler):
    state: AppState

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api(parsed.path, parse_qs(parsed.query))
            return
        self.serve_static(parsed.path)

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"error": message}, status=status)

    def serve_static(self, request_path: str) -> None:
        relative = unquote(request_path).lstrip("/")
        if not relative:
            relative = "index.html"
        path = (self.state.static_dir / relative).resolve()
        static_root = self.state.static_dir.resolve()
        if static_root not in path.parents and path != static_root:
            self.send_error(403)
            return
        if not path.exists() or not path.is_file():
            path = static_root / "index.html"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_api(self, path: str, params: dict[str, list[str]]) -> None:
        if not self.state.db_path.exists():
            self.send_error_json(f"SQLite database not found: {self.state.db_path}", status=404)
            return
        try:
            if path == "/api/summary":
                self.send_json(self.api_summary())
            elif path == "/api/performances":
                self.send_json(self.api_performances(params))
            elif path.startswith("/api/matches/"):
                match_id = as_int(path.rsplit("/", 1)[-1], -1)
                self.send_json(self.api_match(match_id))
            else:
                self.send_error_json("Unknown API route", status=404)
        except sqlite3.Error as exc:
            self.send_error_json(f"SQLite error: {exc}", status=500)

    def api_summary(self) -> dict[str, Any]:
        with connect(self.state.db_path) as connection:
            counts = {
                "matches": connection.execute("SELECT COUNT(*) FROM matches").fetchone()[0],
                "players": connection.execute("SELECT COUNT(*) FROM players").fetchone()[0],
                "items": connection.execute("SELECT COUNT(*) FROM player_items").fetchone()[0],
                "statSamples": connection.execute("SELECT COUNT(*) FROM player_stat_samples").fetchone()[0],
            }
            row = connection.execute(
                """
                SELECT MIN(start_time) AS min_start_time, MAX(start_time) AS max_start_time,
                       MIN(duration_s) AS min_duration_s, MAX(duration_s) AS max_duration_s,
                       MIN(average_badge_team0) AS min_badge0, MAX(average_badge_team0) AS max_badge0,
                       MIN(average_badge_team1) AS min_badge1, MAX(average_badge_team1) AS max_badge1
                FROM matches
                """
            ).fetchone()
        return {
            "counts": counts,
            "range": dict(row),
            "scoreCount": self.state.score_count,
            "durationBias": {
                "message": "Raw standout score favors longer games because it uses cumulative totals.",
                "recommendation": "Use duration filters to compare similar match lengths.",
            },
            "availability": {
                "itemRoute": "available",
                "abilityUpgradeOrder": "available from metadata player item rows with ability assets",
                "statTimelines": "available as cumulative samples",
                "attackTargets": "not present in current match metadata",
                "deathDetails": "available when collected with include_player_death_details",
                "nextDataStep": "Use demo query extraction for target-specific combat events.",
            },
        }

    def api_performances(self, params: dict[str, list[str]]) -> dict[str, Any]:
        limit = min(max(as_int(first(params, "limit"), 60), 1), 200)
        min_percentile = min(max(as_float(first(params, "minPercentile"), 95.0), 0.0), 100.0)
        hero_id = as_int(first(params, "heroId"), 0)
        min_duration_s = optional_int(first(params, "minDurationS"))
        max_duration_s = optional_int(first(params, "maxDurationS"))
        min_kda = optional_float(first(params, "minKda"))
        search = (first(params, "search") or "").strip().lower()

        query = """
            SELECT
              p.match_id, p.player_slot, p.account_id, p.team, p.hero_id, p.hero_name,
              p.kills, p.deaths, p.assists, p.net_worth, p.last_hits, p.denies,
              p.player_level, p.ability_points, p.final_stats_json,
              m.start_time, m.duration_s, m.game_mode, m.match_mode, m.winning_team,
              m.average_badge_team0, m.average_badge_team1,
              CASE WHEN m.winning_team = p.team THEN 1 ELSE 0 END AS won
            FROM players p
            JOIN matches m USING(match_id)
        """
        with connect(self.state.db_path) as connection:
            rows = [dict(row) for row in connection.execute(query)]

        performances = []
        for row in rows:
            duration_s = as_int(row.get("duration_s"))
            if min_duration_s is not None and duration_s < min_duration_s:
                continue
            if max_duration_s is not None and duration_s > max_duration_s:
                continue
            row_kda = kda_ratio(row)
            if min_kda is not None and row_kda < min_kda:
                continue
            if hero_id and as_int(row.get("hero_id")) != hero_id:
                continue
            if search and search not in (row.get("hero_name") or "").lower() and search not in str(row.get("match_id")):
                continue
            key = (as_int(row["match_id"]), as_int(row["player_slot"]))
            percentile = self.state.score_percentiles.get(key, 0.0)
            if percentile < min_percentile:
                continue
            final_stats = json_loads(row.get("final_stats_json")) or {}
            score = performance_score(row)
            performances.append(
                {
                    "matchId": row["match_id"],
                    "playerSlot": row["player_slot"],
                    "heroId": row["hero_id"],
                    "heroName": row["hero_name"],
                    "hero": self.state.hero_assets.get(as_int(row["hero_id"]), {}),
                    "team": row["team"],
                    "won": bool(row["won"]),
                    "score": score,
                    "percentile": percentile,
                    "kills": row["kills"],
                    "deaths": row["deaths"],
                    "assists": row["assists"],
                    "kdaRatio": row_kda,
                    "netWorth": row["net_worth"],
                    "playerDamage": final_stats.get("player_damage"),
                    "bossDamage": final_stats.get("boss_damage"),
                    "healing": final_stats.get("player_healing"),
                    "reasons": performance_reasons(row),
                    "startTime": row["start_time"],
                    "durationS": row["duration_s"],
                    "durationText": mmss(row["duration_s"]),
                    "averageBadge": min(as_int(row["average_badge_team0"]), as_int(row["average_badge_team1"])),
                }
            )
        performances.sort(key=lambda item: (item["percentile"], item["score"]), reverse=True)
        return {
            "items": performances[:limit],
            "totalMatched": len(performances),
            "minPercentile": min_percentile,
            "minDurationS": min_duration_s,
            "maxDurationS": max_duration_s,
            "minKda": min_kda,
        }

    def api_match(self, match_id: int) -> dict[str, Any]:
        with connect(self.state.db_path) as connection:
            match = connection.execute("SELECT * FROM matches WHERE match_id = ?", (match_id,)).fetchone()
            if match is None:
                return {"error": "Match not found"}
            players = dict_rows(
                connection.execute(
                    """
                    SELECT p.*, CASE WHEN m.winning_team = p.team THEN 1 ELSE 0 END AS won
                    FROM players p
                    JOIN matches m USING(match_id)
                    WHERE p.match_id = ?
                    ORDER BY p.team, p.player_slot
                    """,
                    (match_id,),
                )
            )
            items = dict_rows(
                connection.execute(
                    """
                    SELECT * FROM player_items
                    WHERE match_id = ?
                    ORDER BY player_slot, COALESCE(game_time_s, 999999), item_index
                    """,
                    (match_id,),
                )
            )
            samples = dict_rows(
                connection.execute(
                    """
                    SELECT * FROM player_stat_samples
                    WHERE match_id = ?
                    ORDER BY player_slot, time_stamp_s, sample_index
                    """,
                    (match_id,),
                )
            )

        samples_by_player: dict[int, list[dict[str, Any]]] = {}
        for sample in samples:
            raw_sample = json_loads(sample.get("raw_json")) or {}
            sample["ability_points"] = as_int(raw_sample.get("ability_points"), 0)
            sample["timeText"] = mmss(sample.get("time_stamp_s"))
            sample.pop("raw_json", None)
            samples_by_player.setdefault(as_int(sample["player_slot"]), []).append(sample)

        items_by_player: dict[int, list[dict[str, Any]]] = {}
        ability_ranks: dict[tuple[int, int], int] = {}
        for item in items:
            player_slot = as_int(item["player_slot"])
            player_samples = samples_by_player.get(player_slot, [])
            item_id = as_int(item.get("item_id"))
            asset = self.state.item_assets.get(item_id, {})
            item["asset"] = asset
            item["itemKind"] = "ability" if asset.get("type") == "ability" else "shop"
            if item["itemKind"] == "ability":
                rank_key = (player_slot, item_id)
                ability_ranks[rank_key] = ability_ranks.get(rank_key, 0) + 1
                item["abilityRank"] = ability_ranks[rank_key]
                item["abilityStep"] = "unlock" if as_int(item.get("upgrade_id")) == 0 else "upgrade"
            imbued_ability_id = optional_int(item.get("imbued_ability_id"), 1)
            if imbued_ability_id is not None:
                item["imbuedAbility"] = asset_payload(imbued_ability_id, self.state.item_assets, "ability")
            item["timeText"] = mmss(item.get("game_time_s"))
            item["estimatedNetWorthAtBuy"] = estimate_net_worth_at(player_samples, optional_int(item.get("game_time_s")))
            item["estimatedNetWorthAtSell"] = estimate_net_worth_at(player_samples, optional_int(item.get("sold_time_s"), 1))
            item.pop("raw_json", None)
            items_by_player.setdefault(player_slot, []).append(item)

        enriched_players = []
        for player in players:
            player_slot = as_int(player["player_slot"])
            key = (match_id, player_slot)
            final_stats = json_loads(player.get("final_stats_json")) or {}
            hero_id = as_int(player.get("hero_id"))
            player["hero"] = self.state.hero_assets.get(hero_id, {})
            player["items"] = items_by_player.get(player_slot, [])
            player["stats"] = samples_by_player.get(player_slot, [])
            player["finalStats"] = final_stats
            player["deathDetails"] = death_details_for(player)
            player["score"] = performance_score(player)
            player["percentile"] = self.state.score_percentiles.get(key, 0.0)
            player["kdaRatio"] = kda_ratio(player)
            player["reasons"] = performance_reasons(player)
            player["won"] = bool(player.get("won"))
            player.pop("raw_json", None)
            player.pop("final_stats_json", None)
            enriched_players.append(player)

        match_payload = dict(match)
        match_payload["durationText"] = mmss(match_payload.get("duration_s"))
        match_payload["bannedHeroIds"] = json_loads(match_payload.pop("banned_hero_ids_json", None))
        match_payload["objectives"] = json_loads(match_payload.pop("objectives_json", None))
        match_payload["midBoss"] = json_loads(match_payload.pop("mid_boss_json", None))
        match_payload.pop("raw_json", None)
        return {"match": match_payload, "players": enriched_players}


def first(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    return values[0] if values else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the local Deadlock match detail UI.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--asset-manifest", type=Path, default=DEFAULT_ASSET_MANIFEST)
    parser.add_argument("--static-dir", type=Path, default=DEFAULT_STATIC_DIR)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    hero_assets, item_assets = load_assets(args.asset_manifest)
    percentiles, score_count = build_score_percentiles(args.db)
    state = AppState(
        db_path=args.db,
        static_dir=args.static_dir,
        hero_assets=hero_assets,
        item_assets=item_assets,
        score_percentiles=percentiles,
        score_count=score_count,
    )

    class Handler(DeadlockUiHandler):
        pass

    Handler.state = state
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Deadlock match UI running at http://{args.host}:{args.port}")
    print(f"Using database: {args.db}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped Deadlock match UI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
