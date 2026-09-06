#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

DEFAULT_WIKI_BASE_URL = "https://deadlock.wiki"
DEFAULT_ASSET_MANIFEST = Path("assets/deadlock/manifest.json")
DEFAULT_OUTPUT_JSON = Path("assets/deadlock/item_pages.json")


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean_text(value: Any) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def slugify(value: str, fallback: str = "column") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or fallback


def page_slug(value: str) -> str:
    return urllib.parse.quote(str(value).strip().replace(" ", "_"), safe="_()-")


def coerce_value(value: str) -> Any:
    cleaned = clean_text(value)
    if not cleaned or cleaned in {"-", "—", "N/A", "n/a"}:
        return None
    if cleaned.lower() == "true":
        return True
    if cleaned.lower() == "false":
        return False
    if cleaned.startswith("Souls "):
        cleaned = cleaned.removeprefix("Souls ").strip()
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1].strip()
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
    return clean_text(value)


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
class Link:
    href: str
    text: str
    title: str | None = None


@dataclass
class Cell:
    text_parts: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    colspan: int = 1

    @property
    def text(self) -> str:
        return clean_text(" ".join(part for part in self.text_parts if part))


@dataclass
class Table:
    classes: set[str] = field(default_factory=set)
    rows: list[list[Cell]] = field(default_factory=list)


class RichTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self._table_stack: list[Table] = []
        self._current_row: list[Cell] | None = None
        self._current_cell: Cell | None = None
        self._ignored_depth = 0
        self._active_link: dict[str, str | None] | None = None
        self._active_link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "table":
            table = Table(classes=set(str(attr.get("class") or "").split()))
            self._table_stack.append(table)
            if len(self._table_stack) == 1:
                self.tables.append(table)
        elif tag == "tr" and len(self._table_stack) == 1:
            self._current_row = []
        elif tag in {"th", "td"} and self._current_row is not None:
            cell = Cell()
            try:
                cell.colspan = max(1, int(attr.get("colspan") or "1"))
            except ValueError:
                cell.colspan = 1
            self._current_cell = cell
        elif self._current_cell is not None:
            if tag in {"script", "style"}:
                self._ignored_depth += 1
            elif tag == "br":
                self._current_cell.text_parts.append(" ")
            elif tag == "img" and attr.get("alt"):
                self._current_cell.text_parts.append(str(attr["alt"]))
            elif tag == "a" and attr.get("href"):
                self._active_link = {"href": str(attr.get("href") or ""), "title": attr.get("title")}
                self._active_link_text = []

    def handle_endtag(self, tag: str) -> None:
        if self._current_cell is not None and tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag == "a" and self._current_cell is not None and self._active_link:
            text = clean_text(" ".join(self._active_link_text))
            self._current_cell.links.append(Link(self._active_link["href"] or "", text, self._active_link.get("title")))
            self._active_link = None
            self._active_link_text = []
        elif tag == "table" and self._table_stack:
            self._table_stack.pop()
        elif tag == "tr" and self._current_row is not None and len(self._table_stack) == 1:
            if any(cell.text for cell in self._current_row):
                self._table_stack[-1].rows.append(self._current_row)
            self._current_row = None
        elif tag in {"th", "td"} and self._current_cell is not None and self._current_row is not None:
            self._current_row.append(self._current_cell)
            self._current_cell = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is None or self._ignored_depth:
            return
        self._current_cell.text_parts.append(data)
        if self._active_link is not None:
            self._active_link_text.append(data)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[Link] = []
        self._active_link: dict[str, str | None] | None = None
        self._active_link_text: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag in {"script", "style"}:
            self._ignored_depth += 1
        elif tag == "a" and attr.get("href") and not self._ignored_depth:
            self._active_link = {"href": str(attr.get("href") or ""), "title": attr.get("title")}
            self._active_link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag == "a" and self._active_link:
            text = clean_text(" ".join(self._active_link_text))
            self.links.append(Link(self._active_link["href"] or "", text, self._active_link.get("title")))
            self._active_link = None
            self._active_link_text = []

    def handle_data(self, data: str) -> None:
        if self._active_link is not None and not self._ignored_depth:
            self._active_link_text.append(data)


def parse_tables(html: str) -> list[Table]:
    parser = RichTableParser()
    parser.feed(html)
    return parser.tables


def parse_links(html: str) -> list[Link]:
    parser = LinkParser()
    parser.feed(html)
    return parser.links


def expanded_text(row: list[Cell]) -> list[str]:
    values: list[str] = []
    for cell in row:
        values.extend([cell.text] * cell.colspan)
    return values


def expanded_links(row: list[Cell]) -> list[list[Link]]:
    values: list[list[Link]] = []
    for cell in row:
        values.extend([cell.links] * cell.colspan)
    return values


def normalize_href(href: str, wiki_base_url: str) -> str | None:
    if not href or href.startswith(("javascript:", "#")):
        return None
    href = unescape(href)
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        href = wiki_base_url.rstrip("/") + href
    if not href.startswith(("http://", "https://")):
        href = urllib.parse.urljoin(wiki_base_url.rstrip("/") + "/", href)
    return href.split("#", 1)[0]


def link_page_name(link: Link, wiki_base_url: str) -> str | None:
    href = normalize_href(link.href, wiki_base_url)
    if not href:
        return None
    parsed = urllib.parse.urlparse(href)
    base = urllib.parse.urlparse(wiki_base_url)
    if parsed.netloc != base.netloc:
        return None
    page = urllib.parse.unquote(parsed.path.strip("/"))
    if not page or page.startswith(("Special:", "Category:", "File:", "Help:", "Deadlock:", "MediaWiki:", "Talk:")):
        return None
    if parsed.query:
        return None
    return page.replace("_", " ")


def link_payload(link: Link, wiki_base_url: str, item_tokens: dict[str, dict[str, Any]], hero_tokens: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    href = normalize_href(link.href, wiki_base_url)
    page_name = link_page_name(link, wiki_base_url)
    text = clean_text(link.text or link.title or page_name or "")
    if not href or not text:
        return None
    linked_item = item_tokens.get(token(page_name or text))
    linked_hero = hero_tokens.get(token(page_name or text))
    kind = "item" if linked_item else "hero" if linked_hero else "wiki"
    payload = {
        "kind": kind,
        "text": text,
        "page": page_name,
        "url": href,
    }
    if linked_item:
        payload["item"] = linked_item
    if linked_hero:
        payload["hero"] = linked_hero
    return payload


def table_to_payload(table: Table, wiki_base_url: str, item_tokens: dict[str, dict[str, Any]], hero_tokens: dict[str, dict[str, Any]]) -> dict[str, Any]:
    headers = expanded_text(table.rows[0]) if table.rows else []
    keys: list[str] = []
    seen: dict[str, int] = {}
    for index, header in enumerate(headers):
        key = slugify(header, f"column_{index + 1}")
        seen[key] = seen.get(key, 0) + 1
        keys.append(key if seen[key] == 1 else f"{key}_{seen[key]}")

    records: list[dict[str, Any]] = []
    for index, row in enumerate(table.rows[1:], start=1):
        values = expanded_text(row)
        links = expanded_links(row)
        if not any(values):
            continue
        raw: dict[str, str] = {}
        coerced: dict[str, Any] = {}
        row_links: dict[str, list[dict[str, Any]]] = {}
        for cell_index, key in enumerate(keys):
            value = values[cell_index] if cell_index < len(values) else ""
            raw[key] = value
            coerced[key] = coerce_value(value)
            linked = [
                payload for link in (links[cell_index] if cell_index < len(links) else [])
                if (payload := link_payload(link, wiki_base_url, item_tokens, hero_tokens))
            ]
            if linked:
                row_links[key] = linked
        records.append({"row_index": index, "raw": raw, "values": coerced, "links": row_links})
    return {
        "classes": sorted(table.classes),
        "columns": keys,
        "rows": records,
    }


def heading_positions(html: str) -> list[dict[str, Any]]:
    headings = []
    for match in re.finditer(r"<h([23])\b[^>]*>(.*?)</h\1>", html, flags=re.IGNORECASE | re.DOTALL):
        text = clean_text(re.sub(r"<span[^>]+class=\"mw-editsection\".*?</span>", " ", match.group(2), flags=re.IGNORECASE | re.DOTALL))
        if text:
            headings.append({"level": int(match.group(1)), "title": text, "position": match.start()})
    return headings


def section_for(position: int, headings: list[dict[str, Any]]) -> dict[str, str | None]:
    h2 = None
    h3 = None
    for heading in headings:
        if heading["position"] > position:
            break
        if heading["level"] == 2:
            h2 = heading["title"]
            h3 = None
        elif heading["level"] == 3:
            h3 = heading["title"]
    return {"section": h2, "subsection": h3}


def parse_page(item: dict[str, Any], html: str, wiki_base_url: str, item_tokens: dict[str, dict[str, Any]], hero_tokens: dict[str, dict[str, Any]]) -> dict[str, Any]:
    headings = heading_positions(html)
    table_matches = list(re.finditer(r"<table\b.*?</table>", html, flags=re.IGNORECASE | re.DOTALL))
    tables = parse_tables(html)
    table_payloads = []
    for index, table in enumerate(tables):
        position = table_matches[index].start() if index < len(table_matches) else 0
        payload = table_to_payload(table, wiki_base_url, item_tokens, hero_tokens)
        payload.update({"table_index": index + 1, **section_for(position, headings)})
        table_payloads.append(payload)

    links = [
        payload for link in parse_links(html)
        if (payload := link_payload(link, wiki_base_url, item_tokens, hero_tokens))
    ]
    linked_items = {linked["item"]["id"]: linked["item"] for linked in links if linked.get("item", {}).get("id") is not None}
    linked_heroes = {linked["hero"]["id"]: linked["hero"] for linked in links if linked.get("hero", {}).get("id") is not None}
    return {
        "item": item,
        "url": wiki_base_url.rstrip("/") + "/" + page_slug(str(item["name"])),
        "sections": [{"level": heading["level"], "title": heading["title"]} for heading in headings],
        "tables": table_payloads,
        "links": {
            "items": sorted(linked_items.values(), key=lambda row: str(row.get("name") or "")),
            "heroes": sorted(linked_heroes.values(), key=lambda row: str(row.get("name") or "")),
        },
    }


def unique_by_id(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[Any] = set()
    output = []
    for row in rows:
        row_id = row.get("id")
        key = row_id if row_id is not None else token(row.get("name"))
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def build_interaction_index(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    interactions: list[dict[str, Any]] = []
    for page in pages:
        source_item = page["item"]
        source_item_id = source_item.get("id")
        for table in page.get("tables", []):
            if table.get("section") in {None, "Update history"}:
                continue
            for row in table.get("rows", []):
                linked_items = []
                linked_heroes = []
                for links in row.get("links", {}).values():
                    for link in links:
                        item = link.get("item")
                        hero = link.get("hero")
                        if item and item.get("id") != source_item_id:
                            linked_items.append(item)
                        if hero:
                            linked_heroes.append(hero)
                linked_items = unique_by_id(linked_items)
                linked_heroes = unique_by_id(linked_heroes)
                if not linked_items and not linked_heroes:
                    continue
                interactions.append({
                    "source_item": source_item,
                    "section": table.get("section"),
                    "subsection": table.get("subsection"),
                    "table_index": table.get("table_index"),
                    "row_index": row.get("row_index"),
                    "raw": row.get("raw", {}),
                    "values": row.get("values", {}),
                    "linked_items": linked_items,
                    "linked_heroes": linked_heroes,
                })
    return interactions


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "class_name": item.get("class_name"),
        "type": item.get("type"),
        "item_slot_type": item.get("item_slot_type"),
        "item_tier": item.get("item_tier"),
        "cost": item.get("cost"),
        "image": item.get("shop_image") or item.get("image"),
    }


def compact_hero(hero: dict[str, Any]) -> dict[str, Any]:
    images = hero.get("images") if isinstance(hero.get("images"), dict) else {}
    return {
        "id": hero.get("id"),
        "name": hero.get("name"),
        "class_name": hero.get("class_name"),
        "icon": images.get("icon_image_small") or hero.get("icon"),
    }


def load_manifest(path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    raw_items = [item for item in manifest.get("raw", {}).get("items", manifest.get("items", [])) if isinstance(item, dict)]
    raw_heroes = [hero for hero in manifest.get("raw", {}).get("heroes", manifest.get("heroes", [])) if isinstance(hero, dict)]
    items = [
        compact_item(item)
        for item in raw_items
        if item.get("type") == "upgrade" and item.get("shopable") and item.get("name")
    ]
    item_tokens = {token(item["name"]): item for item in items if item.get("name")}
    hero_tokens = {token(hero.get("name")): compact_hero(hero) for hero in raw_heroes if hero.get("name")}
    return items, item_tokens, hero_tokens


def filter_items(items: list[dict[str, Any]], names: list[str], limit: int | None) -> list[dict[str, Any]]:
    if names:
        requested = {token(name) for name in names}
        items = [item for item in items if token(item.get("name")) in requested]
        missing = sorted(requested - {token(item.get("name")) for item in items})
        if missing:
            raise RuntimeError(f"Item not found in manifest: {', '.join(missing)}")
    if limit is not None:
        items = items[:limit]
    return items


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl Deadlock wiki item pages and extract sectioned tables plus item/hero links.")
    parser.add_argument("--wiki-base-url", default=os.getenv("DEADLOCK_WIKI_BASE_URL", DEFAULT_WIKI_BASE_URL))
    parser.add_argument("--asset-manifest", type=Path, default=DEFAULT_ASSET_MANIFEST)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--item", action="append", default=[], help="Crawl one item by exact manifest name. Repeatable. Defaults to every shopable upgrade.")
    parser.add_argument("--limit", type=int, help="Limit crawled items, useful for smoke tests.")
    parser.add_argument("--delay-s", type=float, default=0.15)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    user_agent = os.getenv("DEADLOCK_USER_AGENT", "deadlock-gg-item-page-builder/0.1")
    items, item_tokens, hero_tokens = load_manifest(args.asset_manifest)
    crawl_items = filter_items(items, args.item, args.limit)
    pages = []
    errors = []
    for index, item in enumerate(crawl_items, start=1):
        url = args.wiki_base_url.rstrip("/") + "/" + page_slug(str(item["name"]))
        try:
            html = http_get_text(url, user_agent)
            if "Just a moment..." in html and "challenge-platform" in html and "<table" not in html:
                raise RuntimeError("deadlock.wiki returned a Cloudflare challenge")
            pages.append(parse_page(item, html, args.wiki_base_url, item_tokens, hero_tokens))
            print(json.dumps({"item": item["name"], "tables": len(pages[-1]["tables"]), "page": index, "total": len(crawl_items)}, sort_keys=True), file=sys.stderr)
        except (RuntimeError, urllib.error.URLError) as exc:
            errors.append({"item": item, "url": url, "error": str(exc)})
            print(json.dumps({"item": item["name"], "error": str(exc)}, sort_keys=True), file=sys.stderr)
        if args.delay_s > 0 and index < len(crawl_items):
            time.sleep(args.delay_s)

    interactions = build_interaction_index(pages)
    manifest = {
        "schema_version": 1,
        "generated_at": utc_iso_now(),
        "source": {
            "wiki_base_url": args.wiki_base_url,
            "asset_manifest": str(args.asset_manifest),
            "requested_items": args.item,
            "limit": args.limit,
        },
        "counts": {
            "requested": len(crawl_items),
            "pages": len(pages),
            "errors": len(errors),
            "tables": sum(len(page["tables"]) for page in pages),
            "interactions": len(interactions),
        },
        "interactions": interactions,
        "pages": pages,
        "errors": errors,
    }
    write_json(args.output_json, manifest, args.pretty)
    print(json.dumps({"output": str(args.output_json), **manifest["counts"]}, sort_keys=True))
    return 1 if errors and not pages else 0


if __name__ == "__main__":
    raise SystemExit(main())
