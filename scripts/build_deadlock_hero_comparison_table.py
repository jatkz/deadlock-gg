#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

DEFAULT_SOURCE_URL = "https://deadlock.wiki/Hero_Comparison_Table"
DEFAULT_ASSET_MANIFEST = Path("assets/deadlock/manifest.json")
DEFAULT_OUTPUT_JSON = Path("assets/deadlock/hero_comparison_table.json")
DEFAULT_OUTPUT_CSV = Path("assets/deadlock/hero_comparison_table.csv")


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or fallback


def coerce_value(value: str) -> Any:
    cleaned = clean_text(value)
    if not cleaned or cleaned in {"-", "—", "N/A", "n/a"}:
        return None
    if cleaned.lower() == "true":
        return True
    if cleaned.lower() == "false":
        return False
    if cleaned.endswith("%"):
        number = cleaned[:-1].replace(",", "").strip()
        try:
            return float(number)
        except ValueError:
            return cleaned
    numeric = cleaned.replace(",", "")
    if re.fullmatch(r"-?\d+", numeric):
        try:
            return int(numeric)
        except ValueError:
            return cleaned
    if re.fullmatch(r"-?(?:\d+\.\d*|\d*\.\d+)", numeric):
        try:
            return float(numeric)
        except ValueError:
            return cleaned
    return cleaned


def is_structured_sort_value(value: str | None) -> bool:
    if value is None:
        return False
    coerced = coerce_value(value)
    return coerced is None or isinstance(coerced, (bool, int, float))


def hero_column_key(headers: list[str]) -> str:
    preferred = {"hero", "name", "character"}
    for index, header in enumerate(headers):
        if token(header) in preferred:
            return slugify(header, f"column_{index + 1}")
    return slugify(headers[0] if headers else "hero", "hero")


def http_get_text(url: str, user_agent: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "User-Agent": user_agent,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed with HTTP {exc.code}: {body[:500]}") from exc


@dataclass
class Cell:
    text_parts: list[str] = field(default_factory=list)
    sort_value: str | None = None
    colspan: int = 1

    @property
    def text(self) -> str:
        return clean_text(" ".join(part for part in self.text_parts if part))


@dataclass
class Table:
    classes: set[str] = field(default_factory=set)
    rows: list[list[Cell]] = field(default_factory=list)


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self._table_stack: list[Table] = []
        self._current_row: list[Cell] | None = None
        self._current_cell: Cell | None = None
        self._capture_depth = 0
        self._ignored_cell_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "table":
            classes = set(str(attr.get("class") or "").split())
            table = Table(classes=classes)
            self._table_stack.append(table)
            if len(self._table_stack) == 1:
                self.tables.append(table)
        elif tag == "tr" and len(self._table_stack) == 1:
            self._current_row = []
        elif tag in {"th", "td"} and self._current_row is not None:
            cell = Cell()
            cell.sort_value = attr.get("data-sort-value")
            try:
                cell.colspan = max(1, int(attr.get("colspan") or "1"))
            except ValueError:
                cell.colspan = 1
            self._current_cell = cell
            self._capture_depth = 1
        elif self._current_cell is not None:
            self._capture_depth += 1
            if tag in {"script", "style"}:
                self._ignored_cell_depth += 1
            if tag == "img" and attr.get("alt"):
                self._current_cell.text_parts.append(str(attr["alt"]))
            if tag == "br":
                self._current_cell.text_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._current_cell is not None and tag in {"script", "style"} and self._ignored_cell_depth > 0:
            self._ignored_cell_depth -= 1
        if tag == "table" and self._table_stack:
            self._table_stack.pop()
        elif tag == "tr" and self._current_row is not None and len(self._table_stack) == 1:
            if any(cell.text for cell in self._current_row):
                self._table_stack[-1].rows.append(self._current_row)
            self._current_row = None
        elif tag in {"th", "td"} and self._current_cell is not None and self._current_row is not None:
            self._current_row.append(self._current_cell)
            self._current_cell = None
            self._capture_depth = 0
        elif self._current_cell is not None and self._capture_depth > 0:
            self._capture_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None and self._ignored_cell_depth == 0:
            self._current_cell.text_parts.append(data)


def parse_mediawiki_parse_json(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    parse = payload.get("parse") if isinstance(payload, dict) else None
    if not isinstance(parse, dict):
        return text
    rendered = parse.get("text")
    if isinstance(rendered, dict) and isinstance(rendered.get("*"), str):
        return rendered["*"]
    if isinstance(rendered, str):
        return rendered
    return text


def parse_html_tables(html: str) -> list[Table]:
    parser = TableParser()
    parser.feed(html)
    return parser.tables


def choose_table(tables: list[Table]) -> Table:
    candidates = [
        table
        for table in tables
        if len(table.rows) >= 2 and max((len(row) for row in table.rows), default=0) >= 3
    ]
    if not candidates:
        raise RuntimeError("No data table found in the source HTML.")
    candidates.sort(
        key=lambda table: (
            "wikitable" in table.classes or "sortable" in table.classes,
            len(table.rows),
            max((len(row) for row in table.rows), default=0),
        ),
        reverse=True,
    )
    return candidates[0]


def expanded_text(row: list[Cell]) -> list[str]:
    values: list[str] = []
    for cell in row:
        values.extend([cell.text] * cell.colspan)
    return values


def expanded_sort_values(row: list[Cell]) -> list[str | None]:
    values: list[str | None] = []
    for cell in row:
        value = cell.sort_value
        values.extend([value] * cell.colspan)
    return values


def table_to_rows(table: Table) -> tuple[list[str], list[dict[str, Any]]]:
    raw_headers = expanded_text(table.rows[0])
    headers: list[str] = []
    seen: dict[str, int] = {}
    for index, header in enumerate(raw_headers):
        key = slugify(header, f"column_{index + 1}")
        seen[key] = seen.get(key, 0) + 1
        headers.append(key if seen[key] == 1 else f"{key}_{seen[key]}")

    records: list[dict[str, Any]] = []
    for raw_index, row in enumerate(table.rows[1:], start=1):
        values = expanded_text(row)
        sort_values = expanded_sort_values(row)
        if not any(values):
            continue
        record: dict[str, Any] = {
            "row_index": raw_index,
            "raw": {},
            "values": {},
        }
        for index, key in enumerate(headers):
            raw_value = values[index] if index < len(values) else ""
            sort_value = sort_values[index] if index < len(sort_values) else None
            value_for_coercion = clean_text(sort_value if is_structured_sort_value(sort_value) else raw_value)
            record["raw"][key] = raw_value
            record["values"][key] = coerce_value(value_for_coercion)
        records.append(record)
    return headers, records


def load_hero_assets(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    heroes = manifest.get("heroes", [])
    output: dict[str, dict[str, Any]] = {}
    for hero in heroes:
        if not isinstance(hero, dict):
            continue
        name = hero.get("name")
        if not name:
            continue
        output[token(name)] = {
            "id": hero.get("id"),
            "name": name,
            "class_name": hero.get("class_name"),
            "icon": hero.get("icon"),
            "card": hero.get("card"),
        }
    return output


def enrich_rows(rows: list[dict[str, Any]], headers: list[str], hero_assets: dict[str, dict[str, Any]]) -> None:
    hero_key = hero_column_key(headers)
    for row in rows:
        hero_name = str(row.get("values", {}).get(hero_key) or row.get("raw", {}).get(hero_key) or "").strip()
        base_hero_name = re.sub(r"\s*\([^)]*\)\s*$", "", hero_name).lstrip("+ ").strip()
        asset = hero_assets.get(token(hero_name)) or hero_assets.get(token(base_hero_name))
        row["hero"] = asset or {"name": hero_name}


def build_manifest(source: str, html: str, asset_manifest: Path) -> dict[str, Any]:
    html = parse_mediawiki_parse_json(html)
    table = choose_table(parse_html_tables(html))
    headers, rows = table_to_rows(table)
    hero_assets = load_hero_assets(asset_manifest)
    enrich_rows(rows, headers, hero_assets)
    return {
        "schema_version": 1,
        "generated_at": utc_iso_now(),
        "source": {
            "url": source if source.startswith(("http://", "https://")) else None,
            "file": source if not source.startswith(("http://", "https://")) else None,
            "table_classes": sorted(table.classes),
            "asset_manifest": str(asset_manifest),
        },
        "counts": {
            "columns": len(headers),
            "heroes": len(rows),
            "hero_asset_matches": sum(1 for row in rows if row.get("hero", {}).get("id") is not None),
        },
        "columns": headers,
        "heroes": rows,
    }


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


def write_csv(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["hero_id", "hero_name", *manifest["columns"]]
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in manifest["heroes"]:
            values = dict(row["values"])
            values["hero_id"] = row.get("hero", {}).get("id")
            values["hero_name"] = row.get("hero", {}).get("name")
            writer.writerow(values)
    tmp_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local JSON/CSV manifest from the Deadlock wiki hero comparison table.")
    parser.add_argument("--source-url", default=os.getenv("DEADLOCK_HERO_COMPARISON_URL", DEFAULT_SOURCE_URL))
    parser.add_argument("--source-file", type=Path, help="Read saved HTML or MediaWiki parse JSON from disk instead of fetching.")
    parser.add_argument("--asset-manifest", type=Path, default=DEFAULT_ASSET_MANIFEST)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--no-csv", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    user_agent = os.getenv("DEADLOCK_USER_AGENT", "deadlock-gg-wiki-table-builder/0.1")
    if args.source_file:
        source = str(args.source_file)
        html = args.source_file.read_text(encoding="utf-8")
    else:
        source = args.source_url
        html = http_get_text(args.source_url, user_agent)
        if "Just a moment..." in html and "challenge-platform" in html:
            print(
                "deadlock.wiki returned a Cloudflare challenge. "
                "Open the page in a browser, save the rendered HTML, then rerun with --source-file.",
                file=sys.stderr,
            )
            return 2

    manifest = build_manifest(source, html, args.asset_manifest)
    write_json(args.output_json, manifest, args.pretty)
    if not args.no_csv:
        write_csv(args.output_csv, manifest)
    print(json.dumps({"output": str(args.output_json), **manifest["counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
