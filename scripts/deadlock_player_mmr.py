#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_API_BASE_URL = "https://api.deadlock-api.com"
DEFAULT_ASSET_MANIFEST = Path("assets/deadlock/manifest.json")
STEAM_ID64_OFFSET = 76561197960265728


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def account_id_from_steam_id64(value: str) -> int:
    steam_id64 = int(value)
    account_id = steam_id64 - STEAM_ID64_OFFSET
    if account_id <= 0:
        raise ValueError("SteamID64 did not convert to a positive account id")
    return account_id


def parse_account_id(args: argparse.Namespace) -> int:
    if args.account_id is not None:
        return int(args.account_id)
    if args.steam_id64 is not None:
        return account_id_from_steam_id64(args.steam_id64)
    env_account_id = os.getenv("DEADLOCK_ACCOUNT_ID")
    if env_account_id:
        return int(env_account_id)
    env_steam_id64 = os.getenv("DEADLOCK_STEAM_ID64")
    if env_steam_id64:
        return account_id_from_steam_id64(env_steam_id64)
    raise SystemExit(
        "Missing account id. Use --account-id, --steam-id64, DEADLOCK_ACCOUNT_ID, or DEADLOCK_STEAM_ID64."
    )


def http_get_json(api_base_url: str, path: str, query: dict[str, Any], api_key: str | None, timeout: float) -> Any:
    url = f"{api_base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "deadlock-gg-mmr/0.1",
    }
    if api_key:
        headers["X-API-KEY"] = api_key
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} from {path}: {body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach {path}: {error.reason}") from error


def load_rank_names(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    ranks = manifest.get("ranks", [])
    return {
        int(rank["tier"]): str(rank["name"])
        for rank in ranks
        if isinstance(rank, dict) and rank.get("tier") is not None and rank.get("name")
    }


def rank_label(rank: Any, rank_names: dict[int, str]) -> str:
    if rank is None:
        return "-"
    try:
        rank_value = int(rank)
    except (TypeError, ValueError):
        return str(rank)
    division = rank_value // 10
    tier = rank_value % 10
    name = rank_names.get(division)
    if name:
        return f"{name} {tier} (rank {rank_value})"
    return f"division {division}, tier {tier} (rank {rank_value})"


def unix_time(value: Any) -> str:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return "-"
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def fmt_score(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def latest_entry(entries: Any) -> dict[str, Any] | None:
    if not isinstance(entries, list) or not entries:
        return None
    values = [entry for entry in entries if isinstance(entry, dict)]
    if not values:
        return None
    return max(values, key=lambda entry: int(entry.get("start_time") or 0))


def print_entry(title: str, entry: dict[str, Any], rank_names: dict[int, str]) -> None:
    print(title)
    print(f"  Account: {entry.get('account_id', '-')}")
    print(f"  Rank:    {rank_label(entry.get('rank'), rank_names)}")
    print(f"  Score:   {fmt_score(entry.get('player_score'))}")
    print(f"  Match:   {entry.get('match_id', '-')}")
    print(f"  Time:    {unix_time(entry.get('start_time'))}")


def run(args: argparse.Namespace) -> int:
    load_dotenv()
    account_id = parse_account_id(args)
    api_base_url = args.api_base_url or os.getenv("DEADLOCK_API_BASE_URL", DEFAULT_API_BASE_URL)
    api_key = args.api_key if args.api_key is not None else os.getenv("DEADLOCK_API_KEY")
    rank_names = load_rank_names(args.asset_manifest)

    latest_payload = http_get_json(
        api_base_url,
        "/v1/players/mmr",
        {"account_ids": str(account_id), **({"max_match_id": args.max_match_id} if args.max_match_id else {})},
        api_key,
        args.timeout,
    )
    latest = latest_entry(latest_payload)
    if args.json:
        payload: dict[str, Any] = {"account_id": account_id, "mmr": latest_payload}
    else:
        print("Deadlock API MMR")
        print("  Note: this is the API-derived rank/MMR value, not Valve's hidden internal MMR.")
        if latest:
            print_entry("Latest MMR", latest, rank_names)
        else:
            print("Latest MMR")
            print("  No MMR rows returned for this account.")
        payload = {}

    if not args.no_predict:
        try:
            prediction = http_get_json(
                api_base_url,
                f"/v1/players/{account_id}/rank-predict",
                {},
                api_key,
                args.timeout,
            )
        except RuntimeError as error:
            prediction = {"error": str(error)}
        if args.json:
            payload["rank_predict"] = prediction
        else:
            print()
            print("Rank Prediction")
            if isinstance(prediction, dict) and "error" not in prediction:
                print(f"  Badge:        {rank_label(prediction.get('badge'), rank_names)}")
                print(f"  Raw score:    {fmt_score(prediction.get('raw_score'))}")
                print(f"  Matches used: {prediction.get('matches_used', '-')}")
                print("  Note: prediction is estimated from recent matches and may be inaccurate.")
            else:
                print(f"  Unavailable: {prediction.get('error') if isinstance(prediction, dict) else prediction}")

    if args.history:
        history = http_get_json(api_base_url, f"/v1/players/{account_id}/mmr-history", {}, api_key, args.timeout)
        rows = [entry for entry in history if isinstance(entry, dict)]
        rows.sort(key=lambda entry: int(entry.get("start_time") or 0), reverse=True)
        if args.json:
            payload["history"] = rows[: args.history]
        else:
            print()
            print(f"Recent MMR History ({min(args.history, len(rows))})")
            for entry in rows[: args.history]:
                print(
                    f"  {unix_time(entry.get('start_time'))}  "
                    f"{rank_label(entry.get('rank'), rank_names)}  "
                    f"score {fmt_score(entry.get('player_score'))}  "
                    f"match {entry.get('match_id', '-')}"
                )

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pull a player's Deadlock API MMR/rank.")
    parser.add_argument("--account-id", type=int, help="Deadlock/Steam account id, also called SteamID3 account id.")
    parser.add_argument("--steam-id64", help="Full SteamID64; converted to account id automatically.")
    parser.add_argument("--history", type=int, default=0, help="Also print the N most recent MMR history rows.")
    parser.add_argument("--no-predict", action="store_true", help="Skip the rank prediction endpoint.")
    parser.add_argument("--max-match-id", type=int, help="Ask the MMR endpoint for values at or before this match id.")
    parser.add_argument("--json", action="store_true", help="Print raw JSON output.")
    parser.add_argument("--api-base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--asset-manifest", type=Path, default=DEFAULT_ASSET_MANIFEST)
    parser.add_argument("--timeout", type=float, default=float(os.getenv("DEADLOCK_REQUEST_TIMEOUT_SECONDS", "30")))
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except RuntimeError as error:
        print(f"deadlock_mmr failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
