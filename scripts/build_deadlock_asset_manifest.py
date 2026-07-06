#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_API_BASE_URL = "https://api.deadlock-api.com"
DEFAULT_OUTPUT_DIR = Path("assets/deadlock")


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def http_get_json(base_url: str, path: str, query: dict[str, Any], api_key: str | None, user_agent: str) -> Any:
    clean_query = {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in query.items() if value is not None}
    url = base_url.rstrip("/") + path
    if clean_query:
        url += "?" + urllib.parse.urlencode(clean_query)
    headers = {
        "Accept": "application/json",
        "User-Agent": user_agent,
    }
    if api_key:
        headers["X-API-KEY"] = api_key
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed with HTTP {exc.code}: {body[:500]}") from exc


def write_json(path: Path, data: Any, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        if pretty:
            json.dump(data, handle, indent=2, sort_keys=True)
        else:
            json.dump(data, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
    tmp_path.replace(path)


def compact_hero(hero: dict[str, Any]) -> dict[str, Any]:
    images = hero.get("images") if isinstance(hero.get("images"), dict) else {}
    return {
        "id": hero.get("id"),
        "name": hero.get("name"),
        "class_name": hero.get("class_name"),
        "player_selectable": hero.get("player_selectable"),
        "disabled": hero.get("disabled"),
        "in_development": hero.get("in_development"),
        "icon": images.get("icon_image_small") or images.get("icon_image_small_webp"),
        "card": images.get("icon_hero_card") or images.get("icon_hero_card_webp"),
    }


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "class_name": item.get("class_name"),
        "type": item.get("type"),
        "item_slot_type": item.get("item_slot_type"),
        "item_tier": item.get("item_tier"),
        "cost": item.get("cost"),
        "image": item.get("image") or item.get("image_webp"),
    }


def compact_rank(rank: dict[str, Any]) -> dict[str, Any]:
    images = rank.get("images") if isinstance(rank.get("images"), dict) else {}
    return {
        "tier": rank.get("tier"),
        "name": rank.get("name"),
        "color": rank.get("color"),
        "large": images.get("large") or images.get("large_webp"),
        "small": images.get("small") or images.get("small_webp"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Deadlock hero, item, and rank manifests.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--api-base-url", default=os.getenv("DEADLOCK_API_BASE_URL", DEFAULT_API_BASE_URL))
    parser.add_argument("--api-key", default=os.getenv("DEADLOCK_API_KEY"))
    parser.add_argument("--language", default=os.getenv("DEADLOCK_ASSET_LANGUAGE", "english"))
    parser.add_argument("--client-version", default=os.getenv("DEADLOCK_ASSET_CLIENT_VERSION"))
    parser.add_argument("--include-inactive-heroes", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    user_agent = os.getenv("DEADLOCK_USER_AGENT", "deadlock-gg-asset-builder/0.1")
    common_query = {
        "language": args.language,
        "client_version": args.client_version,
    }
    heroes = http_get_json(
        args.api_base_url,
        "/v1/assets/heroes",
        {**common_query, "only_active": not args.include_inactive_heroes},
        args.api_key,
        user_agent,
    )
    items = http_get_json(args.api_base_url, "/v1/assets/items", common_query, args.api_key, user_agent)
    ranks = http_get_json(args.api_base_url, "/v1/assets/ranks", common_query, args.api_key, user_agent)

    manifest = {
        "schema_version": 1,
        "generated_at": utc_iso_now(),
        "source": {
            "api_base_url": args.api_base_url,
            "language": args.language,
            "client_version": args.client_version,
            "include_inactive_heroes": args.include_inactive_heroes,
        },
        "counts": {
            "heroes": len(heroes),
            "items": len(items),
            "ranks": len(ranks),
        },
        "heroes": [compact_hero(hero) for hero in heroes if isinstance(hero, dict)],
        "items": [compact_item(item) for item in items if isinstance(item, dict)],
        "ranks": [compact_rank(rank) for rank in ranks if isinstance(rank, dict)],
        "raw": {
            "heroes": heroes,
            "items": items,
            "ranks": ranks,
        },
    }
    write_json(args.output_dir / "manifest.json", manifest, args.pretty)
    print(json.dumps({"output": str(args.output_dir / "manifest.json"), **manifest["counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
