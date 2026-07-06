#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, TextIO

STATE_FILE_NAME = "deadlock_match_collector_state.json"
OUTPUT_PREFIX = "deadlock_matches_"
PLAIN_OUTPUT_SUFFIX = ".jsonl"
GZIP_OUTPUT_SUFFIX = ".jsonl.gz"
OUTPUT_SUFFIXES = (PLAIN_OUTPUT_SUFFIX, GZIP_OUTPUT_SUFFIX)
MATCH_TOTAL_CAP_REACHED_EXIT_STATUS = 75
DEFAULT_API_BASE_URL = "https://api.deadlock-api.com"


class RequestBudgetExhausted(Exception):
    pass


@dataclass(frozen=True)
class CollectorConfig:
    api_base_url: str
    api_key: str | None
    data_dir: Path
    scan_mode: str
    game_mode: str | None
    match_mode: str | None
    min_average_badge: int
    min_duration_s: int
    max_duration_s: int | None
    is_high_skill_range_parties: bool | None
    include_player_stats: bool
    include_player_items: bool
    include_player_death_details: bool
    max_requests_per_run: int
    max_matches_per_run: int
    max_matches_total: int
    request_limit: int
    output_records_per_file: int
    retention_days: int
    save_raw_match: bool
    compress_output: bool
    request_timeout: float
    seconds_between_requests: float
    user_agent: str
    log_level: str
    dry_run: bool


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")


def env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def env_optional_bool(name: str) -> bool | None:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return None
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw_value = os.getenv(name)
    value = default if raw_value is None or raw_value.strip() == "" else int(raw_value)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def env_optional_int(name: str) -> int | None:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return None
    return int(raw_value)


def env_float(name: str, default: float, minimum: float | None = None) -> float:
    raw_value = os.getenv(name)
    value = default if raw_value is None or raw_value.strip() == "" else float(raw_value)
    if minimum is not None:
        value = max(minimum, value)
    return value


def env_optional_str(name: str) -> str | None:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return None
    return raw_value.strip()


def log(config: CollectorConfig, message: str, level: str = "info") -> None:
    levels = {
        "quiet": 0,
        "error": 1,
        "info": 2,
        "debug": 3,
    }
    if levels.get(config.log_level, 2) >= levels.get(level, 2):
        print(f"[{iso_now()}] {message}", file=sys.stderr, flush=True)


def output_suffix(compress_output: bool) -> str:
    return GZIP_OUTPUT_SUFFIX if compress_output else PLAIN_OUTPUT_SUFFIX


def output_file_name(date_text: str, part: int, compress_output: bool) -> str:
    return f"{OUTPUT_PREFIX}{date_text}_part{part:04d}{output_suffix(compress_output)}"


def output_date_from_name(file_name: str) -> str | None:
    if not file_name.startswith(OUTPUT_PREFIX):
        return None
    for suffix in OUTPUT_SUFFIXES:
        if file_name.endswith(suffix):
            stem = file_name.removeprefix(OUTPUT_PREFIX).removesuffix(suffix)
            return stem.split("_part", 1)[0]
    return None


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(path)


def open_jsonl_append(path: Path, compress_output: bool) -> TextIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compress_output:
        return gzip.open(path, "at", encoding="utf-8")
    return path.open("a", encoding="utf-8")


def iter_jsonl_records(path: Path) -> Iterable[dict[str, Any]]:
    opener = gzip.open if path.name.endswith(GZIP_OUTPUT_SUFFIX) else open
    try:
        with opener(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    yield value
    except OSError:
        return


def extract_match_id(record: dict[str, Any]) -> int | None:
    value = record.get("match_id")
    if value is None and isinstance(record.get("summary"), dict):
        value = record["summary"].get("match_id")
    if value is None and isinstance(record.get("match"), dict):
        value = record["match"].get("match_id")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def load_state(config: CollectorConfig) -> dict[str, Any]:
    state_path = config.data_dir / STATE_FILE_NAME
    state = read_json(
        state_path,
        {
            "schemaVersion": 1,
            "createdAt": iso_now(),
            "seenMatchIds": [],
            "output": {
                "date": utc_now().date().isoformat(),
                "part": 1,
                "recordsInCurrentFile": 0,
            },
            "matchLimit": {
                "savedTotal": 0,
            },
            "backfill": {
                "nextMaxMatchId": None,
            },
            "lastRun": None,
        },
    )
    if not isinstance(state.get("seenMatchIds"), list):
        state["seenMatchIds"] = []
    if "matchLimit" not in state:
        state["matchLimit"] = {"savedTotal": 0}
    if "output" not in state:
        state["output"] = {"date": utc_now().date().isoformat(), "part": 1, "recordsInCurrentFile": 0}
    if "backfill" not in state:
        state["backfill"] = {"nextMaxMatchId": None}
    return state


def seed_seen_from_existing_files(config: CollectorConfig, state: dict[str, Any]) -> None:
    seen = {str(value) for value in state.get("seenMatchIds", [])}
    saved_total = int(state.get("matchLimit", {}).get("savedTotal", 0) or 0)
    if seen and saved_total > 0:
        return
    for path in sorted(config.data_dir.glob(f"{OUTPUT_PREFIX}*")):
        if not any(path.name.endswith(suffix) for suffix in OUTPUT_SUFFIXES):
            continue
        for record in iter_jsonl_records(path):
            match_id = extract_match_id(record)
            if match_id is not None:
                seen.add(str(match_id))
    state["seenMatchIds"] = sorted(seen, key=int)
    state["matchLimit"]["savedTotal"] = max(saved_total, len(seen))


def current_output_path(config: CollectorConfig, state: dict[str, Any]) -> Path:
    output = state["output"]
    today = utc_now().date().isoformat()
    if output.get("date") != today:
        output["date"] = today
        output["part"] = 1
        output["recordsInCurrentFile"] = 0
    if int(output.get("recordsInCurrentFile", 0) or 0) >= config.output_records_per_file:
        output["part"] = int(output.get("part", 1) or 1) + 1
        output["recordsInCurrentFile"] = 0
    return config.data_dir / output_file_name(output["date"], int(output["part"]), config.compress_output)


def prune_seen_ids(state: dict[str, Any], max_seen_ids: int = 100_000) -> None:
    seen = state.get("seenMatchIds", [])
    if len(seen) > max_seen_ids:
        state["seenMatchIds"] = seen[-max_seen_ids:]


def prune_old_outputs(config: CollectorConfig) -> None:
    if config.retention_days <= 0:
        return
    cutoff = utc_now().date() - timedelta(days=config.retention_days)
    for path in config.data_dir.glob(f"{OUTPUT_PREFIX}*"):
        date_text = output_date_from_name(path.name)
        if not date_text:
            continue
        try:
            file_date = datetime.fromisoformat(date_text).date()
        except ValueError:
            continue
        if file_date < cutoff:
            path.unlink(missing_ok=True)


def http_get_json(config: CollectorConfig, path: str, query: dict[str, Any]) -> Any:
    clean_query: dict[str, str] = {}
    for key, value in query.items():
        if value is None:
            continue
        if isinstance(value, bool):
            clean_query[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple)):
            clean_query[key] = ",".join(str(item) for item in value)
        else:
            clean_query[key] = str(value)

    url = config.api_base_url.rstrip("/") + path
    if clean_query:
        url += "?" + urllib.parse.urlencode(clean_query)

    headers = {
        "Accept": "application/json",
        "User-Agent": config.user_agent,
    }
    if config.api_key:
        headers["X-API-KEY"] = config.api_key
    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=config.request_timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed with HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GET {url} failed: {exc}") from exc

    return json.loads(payload.decode("utf-8"))


def build_metadata_query(config: CollectorConfig, state: dict[str, Any]) -> dict[str, Any]:
    query: dict[str, Any] = {
        "include_info": True,
        "include_more_info": False,
        "include_objectives": True,
        "include_mid_boss": True,
        "include_player_info": True,
        "include_player_kda": True,
        "include_player_items": config.include_player_items,
        "include_player_stats": config.include_player_stats,
        "include_player_final_stats": True,
        "include_player_death_details": config.include_player_death_details,
        "game_mode": config.game_mode,
        "match_mode": config.match_mode,
        "min_duration_s": config.min_duration_s,
        "max_duration_s": config.max_duration_s,
        "min_average_badge": config.min_average_badge,
        "is_high_skill_range_parties": config.is_high_skill_range_parties,
        "is_low_pri_pool": False,
        "is_new_player_pool": False,
        "order_by": "match_id",
        "order_direction": "desc",
        "limit": config.request_limit,
        "format": "json",
    }
    if config.scan_mode == "backfill":
        next_max_match_id = state.get("backfill", {}).get("nextMaxMatchId")
        if next_max_match_id:
            query["max_match_id"] = int(next_max_match_id)
    return query


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


def build_output_record(match: dict[str, Any], query: dict[str, Any], config: CollectorConfig) -> dict[str, Any]:
    record = {
        "schema_version": 1,
        "collected_at": iso_now(),
        "source": {
            "name": "deadlock-api",
            "endpoint": "/v1/matches/metadata",
            "query": query,
        },
        "summary": summarize_match(match),
    }
    if config.save_raw_match:
        record["match"] = match
    return record


def fetch_metadata_page(config: CollectorConfig, state: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    query = build_metadata_query(config, state)
    payload = http_get_json(config, "/v1/matches/metadata", query)
    if not isinstance(payload, list):
        raise RuntimeError(f"Expected metadata list, got {type(payload).__name__}")
    matches = [item for item in payload if isinstance(item, dict)]
    return matches, query


def save_matches(
    config: CollectorConfig,
    state: dict[str, Any],
    matches: list[dict[str, Any]],
    query: dict[str, Any],
) -> int:
    seen = {str(value) for value in state.get("seenMatchIds", [])}
    saved_this_run = 0
    current_path: Path | None = None
    handle: TextIO | None = None

    try:
        for match in matches:
            if config.max_matches_per_run > 0 and saved_this_run >= config.max_matches_per_run:
                break
            if config.max_matches_total > 0 and int(state["matchLimit"].get("savedTotal", 0) or 0) >= config.max_matches_total:
                raise RequestBudgetExhausted()

            match_id = extract_match_id(match)
            if match_id is None:
                continue
            match_id_text = str(match_id)
            if match_id_text in seen:
                continue

            output_record = build_output_record(match, query, config)
            if config.dry_run:
                print(json.dumps(output_record["summary"], sort_keys=True))
            else:
                next_path = current_output_path(config, state)
                if current_path != next_path:
                    if handle is not None:
                        handle.close()
                    current_path = next_path
                    handle = open_jsonl_append(current_path, config.compress_output)
                assert handle is not None
                handle.write(json.dumps(output_record, separators=(",", ":"), sort_keys=True))
                handle.write("\n")
                state["output"]["recordsInCurrentFile"] = int(state["output"].get("recordsInCurrentFile", 0) or 0) + 1
                state["matchLimit"]["savedTotal"] = int(state["matchLimit"].get("savedTotal", 0) or 0) + 1

            seen.add(match_id_text)
            state["seenMatchIds"].append(match_id_text)
            saved_this_run += 1
    finally:
        if handle is not None:
            handle.close()

    prune_seen_ids(state)
    return saved_this_run


def update_backfill_cursor(config: CollectorConfig, state: dict[str, Any], matches: list[dict[str, Any]]) -> None:
    if config.scan_mode != "backfill" or not matches:
        return
    match_ids = [match_id for match in matches if (match_id := extract_match_id(match)) is not None]
    if match_ids:
        state["backfill"]["nextMaxMatchId"] = min(match_ids) - 1


def load_config(args: argparse.Namespace) -> CollectorConfig:
    scan_mode = os.getenv("DEADLOCK_SCAN_MODE", "newest").strip().lower()
    if scan_mode not in {"newest", "backfill"}:
        raise SystemExit("DEADLOCK_SCAN_MODE must be 'newest' or 'backfill'")

    return CollectorConfig(
        api_base_url=os.getenv("DEADLOCK_API_BASE_URL", DEFAULT_API_BASE_URL),
        api_key=env_optional_str("DEADLOCK_API_KEY"),
        data_dir=Path(os.getenv("DEADLOCK_DATA_DIR", "data/deadlock-ranked")),
        scan_mode=scan_mode,
        game_mode=env_optional_str("DEADLOCK_GAME_MODE") or "normal",
        match_mode=env_optional_str("DEADLOCK_MATCH_MODE"),
        min_average_badge=env_int("DEADLOCK_MIN_AVERAGE_BADGE", 84, minimum=0, maximum=116),
        min_duration_s=env_int("DEADLOCK_MIN_DURATION_SECONDS", 720, minimum=0, maximum=7000),
        max_duration_s=env_optional_int("DEADLOCK_MAX_DURATION_SECONDS"),
        is_high_skill_range_parties=env_optional_bool("DEADLOCK_IS_HIGH_SKILL_RANGE_PARTIES"),
        include_player_stats=env_bool("DEADLOCK_INCLUDE_PLAYER_STATS", True),
        include_player_items=env_bool("DEADLOCK_INCLUDE_PLAYER_ITEMS", True),
        include_player_death_details=env_bool("DEADLOCK_INCLUDE_PLAYER_DEATH_DETAILS", True),
        max_requests_per_run=env_int("DEADLOCK_MAX_REQUESTS_PER_RUN", 1, minimum=1),
        max_matches_per_run=env_int("DEADLOCK_MAX_MATCHES_PER_RUN", 250, minimum=0),
        max_matches_total=env_int("DEADLOCK_MAX_MATCHES_TOTAL", 25_000, minimum=0),
        request_limit=env_int("DEADLOCK_REQUEST_LIMIT", 1000, minimum=1, maximum=10_000),
        output_records_per_file=env_int("DEADLOCK_OUTPUT_RECORDS_PER_FILE", 1000, minimum=1),
        retention_days=env_int("DEADLOCK_RETENTION_DAYS", 0, minimum=0),
        save_raw_match=env_bool("DEADLOCK_SAVE_RAW_MATCH", True),
        compress_output=env_bool("DEADLOCK_COMPRESS_OUTPUT", True),
        request_timeout=env_float("DEADLOCK_REQUEST_TIMEOUT_SECONDS", 30.0, minimum=1.0),
        seconds_between_requests=env_float("DEADLOCK_SECONDS_BETWEEN_REQUESTS", 1.0, minimum=0.0),
        user_agent=os.getenv("DEADLOCK_USER_AGENT", "deadlock-gg-collector/0.1"),
        log_level=os.getenv("DEADLOCK_LOG_LEVEL", "info").strip().lower(),
        dry_run=args.dry_run,
    )


def run(config: CollectorConfig) -> int:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(config)
    seed_seen_from_existing_files(config, state)

    started_at = iso_now()
    total_fetched = 0
    total_saved = 0
    last_query: dict[str, Any] | None = None
    last_error: str | None = None
    started_monotonic = time.monotonic()

    log(
        config,
        "collector configured "
        f"scan_mode={config.scan_mode} request_limit={config.request_limit} "
        f"max_requests={config.max_requests_per_run} max_matches={config.max_matches_per_run} "
        f"min_badge={config.min_average_badge} min_duration_s={config.min_duration_s}",
    )

    try:
        for request_index in range(config.max_requests_per_run):
            page_started = time.monotonic()
            matches, query = fetch_metadata_page(config, state)
            last_query = query
            total_fetched += len(matches)
            update_backfill_cursor(config, state, matches)
            saved = save_matches(config, state, matches, query)
            total_saved += saved
            cursor = state.get("backfill", {}).get("nextMaxMatchId")
            saved_total = state.get("matchLimit", {}).get("savedTotal", 0)
            log(
                config,
                f"page {request_index + 1}/{config.max_requests_per_run} "
                f"fetched={len(matches)} saved={saved} total_saved_this_run={total_saved} "
                f"saved_total={saved_total} cursor={cursor} "
                f"elapsed_s={time.monotonic() - page_started:.1f}",
            )

            if config.max_matches_per_run > 0 and total_saved >= config.max_matches_per_run:
                log(config, f"stopping: max matches per run reached ({config.max_matches_per_run})")
                break
            if not matches:
                log(config, "stopping: API returned no matches")
                break
            if config.scan_mode == "newest":
                log(config, "stopping: newest scan mode only reads one page")
                break
            if request_index + 1 < config.max_requests_per_run:
                time.sleep(config.seconds_between_requests)
    except RequestBudgetExhausted:
        log(config, f"stopping: saved-match cap reached ({config.max_matches_total})")
        if not config.dry_run:
            state["lastRun"] = {
                "startedAt": started_at,
                "finishedAt": iso_now(),
                "status": "match_total_cap_reached",
                "fetched": total_fetched,
                "saved": total_saved,
                "query": last_query,
            }
            write_json_atomic(config.data_dir / STATE_FILE_NAME, state)
        return MATCH_TOTAL_CAP_REACHED_EXIT_STATUS
    except Exception as exc:
        last_error = str(exc)
        log(config, f"collector failed: {last_error}", level="error")
        if not config.dry_run:
            state["lastRun"] = {
                "startedAt": started_at,
                "finishedAt": iso_now(),
                "status": "error",
                "error": last_error,
                "fetched": total_fetched,
                "saved": total_saved,
                "query": last_query,
            }
            write_json_atomic(config.data_dir / STATE_FILE_NAME, state)
        raise

    if not config.dry_run:
        prune_old_outputs(config)
        state["lastRun"] = {
            "startedAt": started_at,
            "finishedAt": iso_now(),
            "status": "ok",
            "fetched": total_fetched,
            "saved": total_saved,
            "query": last_query,
            "error": last_error,
        }
        write_json_atomic(config.data_dir / STATE_FILE_NAME, state)

    log(config, f"collector finished fetched={total_fetched} saved={total_saved} elapsed_s={time.monotonic() - started_monotonic:.1f}")
    print(
        json.dumps(
            {
                "status": "ok",
                "dryRun": config.dry_run,
                "scanMode": config.scan_mode,
                "fetched": total_fetched,
                "saved": total_saved,
                "savedTotal": state.get("matchLimit", {}).get("savedTotal", 0),
                "dataDir": str(config.data_dir),
            },
            sort_keys=True,
        )
    )
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect high-skill Deadlock match metadata.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print summaries without writing output.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    config = load_config(args)
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
