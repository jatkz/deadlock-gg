#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_API_BASE_URL = "https://api.deadlock-api.com"
DEFAULT_DB = Path("data/deadlock-analysis/deadlock_matches.sqlite")
DEFAULT_ASSET_MANIFEST = Path("assets/deadlock/manifest.json")
DEFAULT_OUTPUT_DIR = Path("data/deadlock-demo-query")
DEFAULT_FORMAT = "ndjson"
DEFAULT_POLL_INTERVAL_SECONDS = 10.0
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_WAIT_SECONDS = 300


ITEM_USAGE_QUERY = """
SELECT
  tick,
  CAST(NULL AS BIGINT) AS player_slot,
  CAST(NULL AS DOUBLE) AS game_time_s,
  CAST(NULL AS BIGINT) AS ability_id,
  CAST(NULL AS BIGINT) AS item_id,
  'ImportantAbilityUsedEvent' AS event_name,
  caster AS entity_index,
  ability_name,
  CAST(player AS VARCHAR) AS source_player,
  CAST(NULL AS VARCHAR) AS note
FROM ImportantAbilityUsedEvent
UNION ALL
SELECT
  tick,
  CAST(NULL AS BIGINT) AS player_slot,
  CAST(NULL AS DOUBLE) AS game_time_s,
  ability_id,
  ability_id AS item_id,
  'ItemPurchaseNotificationEvent' AS event_name,
  CAST(NULL AS BIGINT) AS entity_index,
  CAST(NULL AS VARCHAR) AS ability_name,
  CAST(userid AS VARCHAR) AS source_player,
  CASE WHEN sell THEN 'sell' WHEN quickbuy THEN 'quickbuy' ELSE 'buy' END AS note
FROM ItemPurchaseNotificationEvent
ORDER BY tick
""".strip()


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def as_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_base_url(value: str) -> str:
    return value.rstrip("/")


def request_headers(api_key: str | None, user_agent: str) -> dict[str, str]:
    headers = {"User-Agent": user_agent}
    if api_key:
        headers["X-API-KEY"] = api_key
    return headers


def http_json(
    method: str,
    api_base_url: str,
    path: str,
    query: dict[str, Any] | None,
    body: Any,
    api_key: str | None,
    user_agent: str,
    timeout: float,
) -> Any:
    url = f"{clean_base_url(api_base_url)}{path}"
    if query:
        clean_query = {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in query.items() if value is not None}
        if clean_query:
            url += "?" + urllib.parse.urlencode(clean_query)
    data = None
    headers = request_headers(api_key, user_agent)
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc


def download_file(url: str, output_path: Path, user_agent: str, timeout: float) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, output_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed with HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GET {url} failed: {exc}") from exc


def load_item_assets(path: Path | None) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    if path is None or not path.exists():
        return {}, {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    by_id: dict[int, dict[str, Any]] = {}
    by_token: dict[str, dict[str, Any]] = {}
    for item in manifest.get("items", []):
        if not isinstance(item, dict):
            continue
        item_id = as_int(item.get("id"))
        if item_id is not None:
            by_id[item_id] = item
        for key in ("class_name", "name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                by_token[value.strip().lower()] = item
    return by_id, by_token


def ensure_demo_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS demo_item_usage_events (
          match_id INTEGER NOT NULL,
          event_index INTEGER NOT NULL,
          player_slot INTEGER,
          tick INTEGER,
          game_time_s REAL,
          ability_id INTEGER,
          item_id INTEGER,
          item_name TEXT,
          asset_class_name TEXT,
          is_active_shop_item INTEGER,
          event_name TEXT,
          entity_index INTEGER,
          ability_name TEXT,
          source TEXT,
          query_job_id TEXT,
          artifact_path TEXT,
          raw_json TEXT,
          imported_at TEXT NOT NULL,
          PRIMARY KEY (match_id, event_index)
        ) WITHOUT ROWID;

        CREATE INDEX IF NOT EXISTS idx_demo_item_usage_match_tick
          ON demo_item_usage_events(match_id, tick);

        CREATE INDEX IF NOT EXISTS idx_demo_item_usage_item
          ON demo_item_usage_events(item_id, match_id);
        """
    )


def artifact_name(match_id: int, job_id: str | None, output_format: str) -> str:
    suffix = "ndjson" if output_format == "ndjson" else output_format
    safe_job_id = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in (job_id or "schema"))
    return f"match_{match_id}_{safe_job_id}.{suffix}"


def schema_cache_name(match_id: int) -> str:
    return f"match_{match_id}_schema.json"


def fetch_schema(args: argparse.Namespace) -> dict[str, Any]:
    query = {"match_id": args.match_id} if args.match_id is not None else {}
    schema = http_json("GET", args.api_base_url, "/v1/matches/demo/schema", query, None, args.api_key, args.user_agent, args.timeout)
    match_id = as_int(schema.get("match_id")) or args.match_id
    if match_id is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        cache_path = args.output_dir / schema_cache_name(match_id)
        cache_path.write_text(json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8")
    return schema


def submit_query(args: argparse.Namespace, query_text: str) -> dict[str, Any]:
    body = {
        "match_id": args.match_id,
        "query": query_text,
        "format": args.format,
    }
    return http_json("POST", args.api_base_url, "/v1/matches/demo/query", None, body, args.api_key, args.user_agent, args.timeout)


def poll_query(args: argparse.Namespace, job_id: str) -> dict[str, Any]:
    started = time.monotonic()
    while True:
        status = http_json("GET", args.api_base_url, f"/v1/matches/demo/query/{urllib.parse.quote(job_id)}", None, None, args.api_key, args.user_agent, args.timeout)
        if status.get("status") in {"done", "failed"}:
            return status
        elapsed = time.monotonic() - started
        if elapsed >= args.max_wait_seconds:
            raise TimeoutError(f"demo query job {job_id} did not finish within {args.max_wait_seconds}s")
        wait = as_float(status.get("estimated_wait_seconds"))
        sleep_for = args.poll_interval_seconds if wait is None else min(args.poll_interval_seconds, max(1.0, wait))
        time.sleep(sleep_for)


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def classify_row(row: dict[str, Any], items_by_id: dict[int, dict[str, Any]], items_by_token: dict[str, dict[str, Any]]) -> dict[str, Any]:
    item_id = as_int(row.get("item_id")) or as_int(row.get("ability_id"))
    asset = items_by_id.get(item_id) if item_id is not None else None
    ability_name = row.get("ability_name")
    if asset is None and isinstance(ability_name, str):
        asset = items_by_token.get(ability_name.strip().lower())
    if asset is not None and item_id is None:
        item_id = as_int(asset.get("id"))
    is_active = asset.get("is_active_item") if isinstance(asset, dict) else None
    return {
        "item_id": item_id,
        "item_name": asset.get("name") if isinstance(asset, dict) else None,
        "asset_class_name": asset.get("class_name") if isinstance(asset, dict) else None,
        "is_active_shop_item": 1 if is_active is True else 0 if is_active is False else None,
    }


def replace_events(
    db_path: Path,
    match_id: int,
    rows: list[dict[str, Any]],
    job_id: str | None,
    artifact_path: Path,
    asset_manifest: Path | None,
) -> int:
    items_by_id, items_by_token = load_item_assets(asset_manifest)
    imported_at = utc_iso_now()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        ensure_demo_schema(connection)
        connection.execute("DELETE FROM demo_item_usage_events WHERE match_id = ?", (match_id,))
        for index, row in enumerate(rows):
            classified = classify_row(row, items_by_id, items_by_token)
            connection.execute(
                """
                INSERT INTO demo_item_usage_events (
                  match_id, event_index, player_slot, tick, game_time_s, ability_id, item_id,
                  item_name, asset_class_name, is_active_shop_item, event_name, entity_index,
                  ability_name, source, query_job_id, artifact_path, raw_json, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    index,
                    as_int(row.get("player_slot")),
                    as_int(row.get("tick")),
                    as_float(row.get("game_time_s")),
                    as_int(row.get("ability_id")),
                    classified["item_id"],
                    classified["item_name"],
                    classified["asset_class_name"],
                    classified["is_active_shop_item"],
                    row.get("event_name"),
                    as_int(row.get("entity_index")),
                    row.get("ability_name"),
                    row.get("source_player") or row.get("source"),
                    job_id,
                    str(artifact_path),
                    as_json(row),
                    imported_at,
                ),
            )
        connection.commit()
    return len(rows)


def query_text_from_args(args: argparse.Namespace) -> str:
    if args.query_file:
        return args.query_file.read_text(encoding="utf-8").strip()
    if args.query:
        return args.query.strip()
    return ITEM_USAGE_QUERY


def command_schema(args: argparse.Namespace) -> int:
    schema = fetch_schema(args)
    tables = schema.get("tables") if isinstance(schema.get("tables"), list) else []
    event_tables = [table for table in tables if table.get("kind") == "event"]
    item_tables = [
        table
        for table in tables
        if any(token in str(table.get("name", "")).lower() for token in ("item", "upgrade", "ability"))
    ]
    print(
        json.dumps(
            {
                "match_id": schema.get("match_id"),
                "demo_url": schema.get("demo_url"),
                "tables": len(tables),
                "event_tables": len(event_tables),
                "item_or_ability_tables": len(item_tables),
                "schema_cache": str(args.output_dir / schema_cache_name(as_int(schema.get("match_id")) or 0)),
            },
            sort_keys=True,
        )
    )
    return 0


def command_run(args: argparse.Namespace) -> int:
    if args.print_query:
        print(query_text_from_args(args))
        return 0
    if args.match_id is None:
        raise SystemExit("--match-id is required for run")

    schema = fetch_schema(args) if not args.skip_schema else None
    query_text = query_text_from_args(args)
    if args.no_submit:
        print(json.dumps({"status": "ok", "schemaMatchId": schema.get("match_id") if schema else None, "submitted": False}, sort_keys=True))
        return 0

    submission = submit_query(args, query_text)
    job_id = str(submission.get("job_id") or "")
    if not job_id:
        raise RuntimeError(f"demo query submission did not return job_id: {submission}")
    status = poll_query(args, job_id)
    if status.get("status") != "done":
        raise RuntimeError(f"demo query job {job_id} failed: {status.get('error') or status}")
    result_url = status.get("result_url")
    if not isinstance(result_url, str) or not result_url:
        raise RuntimeError(f"demo query job {job_id} finished without result_url")

    artifact_path = args.output_dir / artifact_name(args.match_id, job_id, args.format)
    download_file(result_url, artifact_path, args.user_agent, args.timeout)
    inserted = None
    if args.format == "ndjson" and not args.no_ingest:
        rows = read_ndjson(artifact_path)
        inserted = replace_events(args.db, args.match_id, rows, job_id, artifact_path, args.asset_manifest)

    print(
        json.dumps(
            {
                "status": "ok",
                "match_id": args.match_id,
                "job_id": job_id,
                "artifact": str(artifact_path),
                "inserted_events": inserted,
            },
            sort_keys=True,
        )
    )
    return 0


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--match-id", type=int)
    parser.add_argument("--api-base-url", default=os.getenv("DEADLOCK_API_BASE_URL", DEFAULT_API_BASE_URL))
    parser.add_argument("--api-key", default=os.getenv("DEADLOCK_API_KEY"))
    parser.add_argument("--user-agent", default=os.getenv("DEADLOCK_USER_AGENT", "deadlock-gg-demo-query/0.1"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=float, default=float(os.getenv("DEADLOCK_REQUEST_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Deadlock API demo-query spikes and ingest item usage events.")
    subparsers = parser.add_subparsers(dest="command")

    schema_parser = subparsers.add_parser("schema", help="Fetch and cache the demo query schema.")
    add_common_args(schema_parser)
    schema_parser.set_defaults(func=command_schema)

    run_parser = subparsers.add_parser("run", help="Submit, poll, download, and optionally ingest a demo query.")
    add_common_args(run_parser)
    run_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    run_parser.add_argument("--asset-manifest", type=Path, default=DEFAULT_ASSET_MANIFEST)
    run_parser.add_argument("--format", choices=("ndjson", "parquet"), default=DEFAULT_FORMAT)
    run_parser.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    run_parser.add_argument("--max-wait-seconds", type=int, default=DEFAULT_MAX_WAIT_SECONDS)
    run_parser.add_argument("--query-file", type=Path)
    run_parser.add_argument("--query")
    run_parser.add_argument("--print-query", action="store_true")
    run_parser.add_argument("--skip-schema", action="store_true")
    run_parser.add_argument("--no-submit", action="store_true", help="Fetch schema and stop before queuing a demo query.")
    run_parser.add_argument("--no-ingest", action="store_true", help="Download the artifact without writing SQLite rows.")
    run_parser.set_defaults(func=command_run)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        raise SystemExit(2)
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        return args.func(args)
    except (RuntimeError, TimeoutError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
