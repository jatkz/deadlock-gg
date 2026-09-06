#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import math
import mimetypes
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

DEFAULT_DB = Path("data/deadlock-analysis/deadlock_matches.sqlite")
DEFAULT_ASSET_MANIFEST = Path("assets/deadlock/manifest.json")
DEFAULT_HERO_COMPARISON_TABLE = Path("assets/deadlock/hero_comparison_table.json")
DEFAULT_STATIC_DIR = Path("ui")
DEFAULT_SAVED_MATCHES_FILE = Path("data/deadlock-saved/saved_matches.jsonl")


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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
    minutes, secs = divmod(round(max(0, seconds)), 60)
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


def badge_label(value: Any, name: Any) -> str | None:
    badge_value = optional_int(value)
    if badge_value is None or badge_value <= 0:
        return None
    badge_name = str(name or "").strip()
    if badge_name:
        return badge_name
    division = badge_value // 10
    subtier = badge_value % 10
    return f"Badge {division} {subtier}" if subtier else f"Badge {division}"


def match_badge_payload(row: dict[str, Any]) -> dict[str, Any]:
    team0_value = optional_int(row.get("average_badge_team0"))
    team1_value = optional_int(row.get("average_badge_team1"))
    team0_label = badge_label(team0_value, row.get("average_badge_team0_name"))
    team1_label = badge_label(team1_value, row.get("average_badge_team1_name"))
    numeric_values = [value for value in (team0_value, team1_value) if value is not None and value > 0]
    labels = [label for label in (team0_label, team1_label) if label]
    return {
        "team0": {"value": team0_value if team0_value and team0_value > 0 else None, "label": team0_label},
        "team1": {"value": team1_value if team1_value and team1_value > 0 else None, "label": team1_label},
        "averageValue": min(numeric_values) if numeric_values else None,
        "label": " / ".join(labels) if labels else None,
    }


def split_tokens(value: str | None) -> list[str]:
    return [token.strip().lower() for token in (value or "").replace("\n", ",").split(",") if token.strip()]


def wilson_interval(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    rate = wins / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((rate * (1 - rate) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def hero_matches_token(hero_id: Any, hero_name: Any, token: str) -> bool:
    if not token:
        return True
    return token in str(hero_name or "").lower() or str(hero_id or "") == token


def item_matches_token(item_id: Any, item_name: Any, token: str) -> bool:
    if not token:
        return True
    return token in str(item_name or "").lower() or str(item_id or "") == token


def search_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    without_svg = re.sub(r"<svg\b.*?</svg>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_svg)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


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


STAT_GROUPS = {
    "Vitality": ("health", "armor", "regen", "barrier", "resist"),
    "Weapon": ("weapon", "bullet", "clip", "round", "rounds", "reload", "fire", "melee", "dps", "ammo"),
    "Spirit": ("tech", "spirit", "ability"),
    "Mobility": ("move", "speed", "dash", "stamina", "sprint", "jump", "slide", "air", "crouch"),
}

IMPORTANT_PROPERTY_TOKENS = (
    "damage",
    "range",
    "radius",
    "cooldown",
    "duration",
    "charge",
    "cast",
    "channel",
    "speed",
    "stamina",
    "health",
    "fire",
    "ammo",
    "bullet",
)

ABILITY_SHEET_METRICS = {
    "damage": ("damage",),
    "cooldown": ("cooldown",),
    "range": ("range",),
    "radius": ("radius", "aoe"),
}

TOTAL_DAMAGE_DIRECT_KEYS = ("Damage", "BonusDamage")
TOTAL_DAMAGE_UPGRADE_NAME_TOKENS = ("damage",)
TOTAL_DAMAGE_DOT_KEYS = (
    "DPS",
    "FireDPS",
    "TurretDPS",
    "SummonDPS",
    "BarbedWireDPS",
    "CreepDPS",
)
TOTAL_DAMAGE_DURATION_KEYS = (
    "BurnDuration",
    "FireDuration",
    "BloodSpillDuration",
    "DebuffDuration",
    "DamageDuration",
    "AbilityDuration",
    "Duration",
)


def display_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("E") and len(text) > 1 and text[1].isupper():
        text = text[1:]
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    text = text.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip().title()


def label_words(*values: Any) -> set[str]:
    text = " ".join(str(value or "") for value in values)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def normalize_stat_entry(key: str, payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        value = payload.get("value")
        label = payload.get("label") or payload.get("display_stat_name") or key
    else:
        value = payload
        label = key
    if value in (None, ""):
        return None
    return {"key": key, "label": display_label(label), "value": value}


def group_stats(stats: Any) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {name: [] for name in STAT_GROUPS}
    groups["Other"] = []
    if not isinstance(stats, dict):
        return groups
    for key, payload in sorted(stats.items()):
        entry = normalize_stat_entry(key, payload)
        if entry is None:
            continue
        words = label_words(key, entry["label"])
        group_name = next(
            (name for name, tokens in STAT_GROUPS.items() if any(token in words for token in tokens)),
            "Other",
        )
        groups[group_name].append(entry)
    return {name: values for name, values in groups.items() if values}


def property_value_text(prop: dict[str, Any]) -> str:
    value = prop.get("value")
    if value in (None, ""):
        return ""
    text = str(value).strip()
    postfix = str(prop.get("postfix") or "").strip()
    if postfix and not text.endswith(postfix):
        text = f"{text}{postfix}"
    return text


def property_label_for(properties: dict[str, Any], name: str) -> str:
    payload = properties.get(name)
    if isinstance(payload, dict):
        return display_label(payload.get("label") or payload.get("postvalue_label") or name)
    return display_label(name)


def property_suffix_for(properties: dict[str, Any], name: str) -> str:
    payload = properties.get(name)
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("postfix") or "").strip()


def upgrade_bonus_text(properties: dict[str, Any], upgrade: dict[str, Any]) -> str:
    name = str(upgrade.get("name") or "").strip()
    bonus = str(upgrade.get("bonus") or "").strip()
    if not name or not bonus:
        return ""
    prefix = "" if bonus.startswith(("+", "-")) else "+"
    suffix = property_suffix_for(properties, name)
    return f"{prefix}{bonus}{suffix} {property_label_for(properties, name)}"


def numeric_parts(value: Any) -> tuple[float | None, str]:
    text = str(value or "").strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None, ""
    suffix = text[match.end():].strip()
    return float(match.group(0)), suffix


def format_stat_value(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    if abs(value - round(value)) < 0.001:
        text = str(int(round(value)))
    else:
        text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def normalize_upgrades(item: dict[str, Any], descriptions: dict[str, str]) -> list[dict[str, Any]]:
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    raw_upgrades = item.get("upgrades") if isinstance(item.get("upgrades"), list) else []
    tiers = []
    for index in range(max(3, len(raw_upgrades))):
        tier = index + 1
        raw_upgrade = raw_upgrades[index] if index < len(raw_upgrades) and isinstance(raw_upgrades[index], dict) else {}
        property_upgrades = [
            text for upgrade in raw_upgrade.get("property_upgrades", [])
            if isinstance(upgrade, dict) and (text := upgrade_bonus_text(properties, upgrade))
        ]
        desc = descriptions.get(f"t{tier}_desc") or ""
        if not desc and property_upgrades:
            desc = ", ".join(property_upgrades)
        if desc or property_upgrades:
            tiers.append({
                "tier": tier,
                "description": desc,
                "propertyUpgrades": property_upgrades,
                "raw": raw_upgrade,
            })
    return tiers


def property_matches_metric(key: str, prop: dict[str, Any], metric: str) -> bool:
    words = label_words(key, prop.get("label"), prop.get("postvalue_label"), prop.get("css_class"))
    return any(token in words for token in ABILITY_SHEET_METRICS[metric])


def metric_property(item: dict[str, Any], metric: str) -> tuple[str, dict[str, Any]] | None:
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    preferred = {
        "damage": ("Damage", "WeaponDamage", "BaseAttackDamage"),
        "cooldown": ("AbilityCooldown",),
        "range": ("AbilityCastRange", "CastRange", "RicochetRange"),
        "radius": ("Radius", "AOERadius", "DamageRadius", "ExplodeRadius"),
    }
    for key in preferred[metric]:
        prop = properties.get(key)
        if isinstance(prop, dict) and property_value_text(prop):
            return key, prop
    for key, prop in properties.items():
        if isinstance(prop, dict) and property_value_text(prop) and property_matches_metric(key, prop, metric):
            return key, prop
    return None


def upgrade_effects_for_property(item: dict[str, Any], property_key: str, upgrade_tiers: int) -> dict[str, Any]:
    base_delta = 0.0
    scale_delta = 0.0
    scale_multiplier = 1.0
    notes = []
    upgrades = item.get("upgrades") if isinstance(item.get("upgrades"), list) else []
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    for raw_upgrade in upgrades[:max(0, upgrade_tiers)]:
        if not isinstance(raw_upgrade, dict):
            continue
        for change in raw_upgrade.get("property_upgrades", []):
            if not isinstance(change, dict) or change.get("name") != property_key:
                continue
            value, _suffix = numeric_parts(change.get("bonus"))
            if value is None:
                continue
            upgrade_type = str(change.get("upgrade_type") or "EAddToBase")
            if upgrade_type == "EAddToScale":
                scale_delta += value
                notes.append(f"+{format_stat_value(value)} scaling for {property_label_for(properties, property_key)}")
            elif upgrade_type == "EMultiplyScale":
                scale_multiplier *= value
                notes.append(f"x{format_stat_value(value)} scaling for {property_label_for(properties, property_key)}")
            elif upgrade_type == "EMultiplyBase":
                base_delta += value
                notes.append(upgrade_bonus_text(properties, change))
            else:
                base_delta += value
                notes.append(upgrade_bonus_text(properties, change))
    return {
        "baseDelta": base_delta,
        "scaleDelta": scale_delta,
        "scaleMultiplier": scale_multiplier,
        "notes": notes,
    }


def upgrade_delta_for_property(item: dict[str, Any], property_key: str, upgrade_tiers: int) -> tuple[float, list[str]]:
    effects = upgrade_effects_for_property(item, property_key, upgrade_tiers)
    return effects["baseDelta"], effects["notes"]


def scaled_metric_value(
    item: dict[str, Any],
    property_key: str,
    prop: dict[str, Any],
    base_value: float | None,
    player_sample: dict[str, Any],
    include_scaling: bool,
    scale_delta: float = 0.0,
    scale_multiplier: float = 1.0,
) -> tuple[float | None, list[str]]:
    if base_value is None or not include_scaling:
        return base_value, []
    scale_function = prop.get("scale_function") if isinstance(prop.get("scale_function"), dict) else {}
    class_name = str(scale_function.get("class_name") or "")
    stat_scale = optional_float(scale_function.get("stat_scale"))
    notes = []
    value = base_value
    if class_name == "scale_function_tech_damage" and stat_scale is not None:
        tech_power = as_float(player_sample.get("tech_power"))
        final_scale = (stat_scale * scale_multiplier) + scale_delta
        value += tech_power * final_scale
        notes.append(f"+{format_stat_value(tech_power * final_scale)} from {format_stat_value(tech_power)} tech power x {format_stat_value(final_scale)} scale")
    return value, notes


def property_numeric_value(
    item: dict[str, Any],
    property_key: str,
    upgrade_tiers: int,
    player_sample: dict[str, Any],
    include_scaling: bool,
) -> tuple[float | None, str, list[str]]:
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    prop = properties.get(property_key)
    if not isinstance(prop, dict):
        return None, "", []
    base_value, suffix = numeric_parts(property_value_text(prop))
    if not suffix:
        suffix = str(prop.get("postfix") or "").strip()
    if base_value is None:
        return None, suffix, []
    effects = upgrade_effects_for_property(item, property_key, upgrade_tiers)
    value, scaling_notes = scaled_metric_value(
        item,
        property_key,
        prop,
        base_value + effects["baseDelta"],
        player_sample,
        include_scaling,
        effects["scaleDelta"],
        effects["scaleMultiplier"],
    )
    return value, suffix, [*effects["notes"], *scaling_notes]


def first_numeric_property(
    item: dict[str, Any],
    property_keys: tuple[str, ...],
    upgrade_tiers: int,
    player_sample: dict[str, Any],
    include_scaling: bool,
    prefer_nonzero: bool = False,
) -> tuple[str, float, str, list[str]] | None:
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    first_match = None
    for key in property_keys:
        if key not in properties:
            continue
        value, suffix, notes = property_numeric_value(item, key, upgrade_tiers, player_sample, include_scaling)
        if value is not None:
            match = (key, value, suffix, notes)
            if not prefer_nonzero or abs(value) > 0.001:
                return match
            if first_match is None:
                first_match = match
    return first_match


def ability_total_damage_value(
    item: dict[str, Any],
    upgrade_tiers: int,
    player_sample: dict[str, Any],
    include_scaling: bool,
) -> dict[str, Any]:
    direct = first_numeric_property(item, TOTAL_DAMAGE_DIRECT_KEYS, upgrade_tiers, player_sample, include_scaling)
    dot = first_numeric_property(item, TOTAL_DAMAGE_DOT_KEYS, upgrade_tiers, player_sample, include_scaling)
    duration = first_numeric_property(item, TOTAL_DAMAGE_DURATION_KEYS, upgrade_tiers, player_sample, include_scaling, True)
    direct_value = direct[1] if direct else 0.0
    dot_value = dot[1] if dot else 0.0
    duration_value = duration[1] if duration else 0.0
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    extra_direct_damage = 0.0
    extra_notes = []
    primary_direct_key = direct[0] if direct else ""
    upgrades = item.get("upgrades") if isinstance(item.get("upgrades"), list) else []
    seen_extra_damage_keys = set()
    for raw_upgrade in upgrades[:max(0, upgrade_tiers)]:
        if not isinstance(raw_upgrade, dict):
            continue
        for change in raw_upgrade.get("property_upgrades", []):
            if not isinstance(change, dict):
                continue
            name = str(change.get("name") or "")
            if name == primary_direct_key or not any(token in name.lower() for token in TOTAL_DAMAGE_UPGRADE_NAME_TOKENS):
                continue
            if name in seen_extra_damage_keys:
                continue
            seen_extra_damage_keys.add(name)
            prop = properties.get(name)
            if isinstance(prop, dict) and property_value_text(prop):
                continue
            effects = upgrade_effects_for_property(item, name, upgrade_tiers)
            value = effects["baseDelta"]
            if abs(value) <= 0.001:
                continue
            extra_direct_damage += value
            extra_notes.extend(effects["notes"])

    if not direct and not dot and not extra_direct_damage:
        return {"value": "-", "base": "-", "notes": ["No direct damage or DPS property found."]}
    total = direct_value + extra_direct_damage + dot_value * duration_value
    notes = []
    if direct:
        notes.append(f"{format_stat_value(direct_value)} {property_label_for(item.get('properties') or {}, direct[0])}")
        notes.extend(direct[3])
    if extra_direct_damage:
        notes.append(f"{format_stat_value(extra_direct_damage)} extra damage upgrades")
        notes.extend(extra_notes)
    if dot:
        notes.append(f"{format_stat_value(dot_value)} DPS from {dot[0]}")
        notes.extend(dot[3])
    if dot and duration:
        notes.append(f"{format_stat_value(duration_value, duration[2])} duration from {duration[0]}")
        notes.extend(duration[3])
    elif dot:
        notes.append("No duration property found, so DPS contribution is 0.")
    return {
        "value": format_stat_value(total),
        "base": "-",
        "propertyKey": "TotalDamage",
        "formula": "damage + dps * duration",
        "notes": notes,
    }


def ability_metric_value(
    item: dict[str, Any],
    metric: str,
    upgrade_tiers: int,
    player_sample: dict[str, Any],
    include_scaling: bool,
) -> dict[str, Any]:
    found = metric_property(item, metric)
    if found is None:
        return {"value": "-", "base": "-", "notes": []}
    property_key, prop = found
    base_value, suffix = numeric_parts(property_value_text(prop))
    if not suffix:
        suffix = str(prop.get("postfix") or "").strip()
    upgrade_delta, upgrade_notes = upgrade_delta_for_property(item, property_key, upgrade_tiers)
    upgraded_value = base_value + upgrade_delta if base_value is not None else None
    scaled_value, scaling_notes = scaled_metric_value(item, property_key, prop, upgraded_value, player_sample, include_scaling)
    return {
        "value": format_stat_value(scaled_value, suffix),
        "base": format_stat_value(base_value, suffix),
        "propertyKey": property_key,
        "upgradeDelta": format_stat_value(upgrade_delta, suffix) if upgrade_delta else "",
        "notes": [*upgrade_notes, *scaling_notes],
    }


def normalize_property(key: str, payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    value_text = property_value_text(payload)
    if not value_text:
        return None
    disable_value = str(payload.get("disable_value") or "").strip()
    if disable_value and value_text == disable_value:
        return None
    label = display_label(payload.get("label") or payload.get("postvalue_label") or key)
    haystack = f"{key} {label} {payload.get('css_class') or ''}".lower()
    if not any(token in haystack for token in IMPORTANT_PROPERTY_TOKENS):
        return None
    return {
        "key": key,
        "label": label,
        "value": value_text,
        "cssClass": payload.get("css_class") or "",
        "scale": payload.get("scale_function") if isinstance(payload.get("scale_function"), dict) else None,
    }


def normalize_item_asset(
    item: dict[str, Any] | None,
    compact_assets: dict[int, dict[str, Any]],
    raw_item_assets_by_class: dict[str, dict[str, Any]] | None = None,
    include_dependents: bool = False,
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    item_id = optional_int(item.get("id"))
    compact = compact_assets.get(item_id or -1, {})
    properties = [
        prop for key, value in sorted((item.get("properties") or {}).items())
        if (prop := normalize_property(key, value)) is not None
    ]
    descriptions = {
        key: text
        for key, value in sorted((item.get("description") or {}).items())
        if (text := clean_text(value))
    }
    dependent_abilities = []
    if include_dependents and raw_item_assets_by_class:
        raw_dependents = item.get("dependent_abilities") if isinstance(item.get("dependent_abilities"), dict) else {}
        for class_name, metadata in sorted(raw_dependents.items()):
            flags = metadata.get("flags") if isinstance(metadata, dict) else []
            if "DisplayAsSubAbility" not in flags:
                continue
            dependent = normalize_item_asset(
                raw_item_assets_by_class.get(str(class_name)),
                compact_assets,
                raw_item_assets_by_class,
                False,
            )
            if dependent is not None:
                dependent["linkFlags"] = flags
                dependent_abilities.append(dependent)
    return {
        "id": item_id,
        "name": item.get("name") or item.get("class_name") or str(item_id or ""),
        "className": item.get("class_name") or "",
        "type": item.get("type") or "",
        "image": compact.get("image") or item.get("image") or item.get("image_webp") or "",
        "properties": properties,
        "descriptions": descriptions,
        "upgrades": normalize_upgrades(item, descriptions),
        "dependentAbilities": dependent_abilities,
        "raw": item,
    }


def hero_summary_payload(hero: dict[str, Any], compact_assets: dict[int, dict[str, Any]]) -> dict[str, Any]:
    hero_id = as_int(hero.get("id"))
    compact = compact_assets.get(hero_id, {})
    images = hero.get("images") if isinstance(hero.get("images"), dict) else {}
    return {
        "id": hero_id,
        "name": hero.get("name") or compact.get("name") or str(hero_id),
        "className": hero.get("class_name") or "",
        "heroType": hero.get("hero_type") or "",
        "complexity": hero.get("complexity"),
        "icon": compact.get("icon") or images.get("icon_image_small") or images.get("icon_image_small_webp") or "",
        "card": compact.get("card") or images.get("icon_hero_card") or images.get("icon_hero_card_webp") or "",
        "disabled": bool(hero.get("disabled")),
        "playerSelectable": bool(hero.get("player_selectable")),
    }


def truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class AppState:
    db_path: Path
    static_dir: Path
    saved_matches_file: Path
    hero_comparison_table: dict[str, Any]
    hero_assets: dict[int, dict[str, Any]]
    item_assets: dict[int, dict[str, Any]]
    raw_hero_assets: dict[int, dict[str, Any]]
    raw_item_assets_by_class: dict[str, dict[str, Any]]
    raw_item_assets_by_id: dict[int, dict[str, Any]]
    score_percentiles: dict[tuple[int, int], float]
    score_count: int


def load_assets(
    path: Path,
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[str, dict[str, Any]], dict[int, dict[str, Any]]]:
    if not path.exists():
        return {}, {}, {}, {}, {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    raw_heroes = [
        hero for hero in manifest.get("raw", {}).get("heroes", manifest.get("heroes", []))
        if isinstance(hero, dict)
    ]
    raw_items = [
        item for item in manifest.get("raw", {}).get("items", manifest.get("items", []))
        if isinstance(item, dict)
    ]
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
    raw_hero_assets = {
        int(hero["id"]): hero
        for hero in raw_heroes
        if hero.get("id") is not None
    }
    raw_item_assets_by_class = {
        str(item["class_name"]): item
        for item in raw_items
        if item.get("class_name")
    }
    raw_item_assets_by_id = {
        int(item["id"]): item
        for item in raw_items
        if item.get("id") is not None
    }
    return heroes, items, raw_hero_assets, raw_item_assets_by_class, raw_item_assets_by_id


def load_hero_comparison_table(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": 1,
            "source": {"file": str(path), "missing": True},
            "counts": {"columns": 0, "heroes": 0, "hero_asset_matches": 0},
            "columns": [],
            "heroes": [],
        }
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return manifest if isinstance(manifest, dict) else {}


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def extract_saved_match_id(record: dict[str, Any]) -> int | None:
    for value in (
        record.get("match_id"),
        record.get("summary", {}).get("match_id") if isinstance(record.get("summary"), dict) else None,
        record.get("match", {}).get("match_id") if isinstance(record.get("match"), dict) else None,
    ):
        match_id = optional_int(value)
        if match_id is not None:
            return match_id
    return None


def load_saved_match_records(path: Path) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            match_id = extract_saved_match_id(record)
            if match_id is not None:
                records[match_id] = record
    return records


def write_saved_match_records(path: Path, records: dict[int, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for match_id in sorted(records, reverse=True):
            handle.write(json.dumps(records[match_id], separators=(",", ":"), sort_keys=True))
            handle.write("\n")
    tmp_path.replace(path)


def summarize_saved_match(match: dict[str, Any]) -> dict[str, Any]:
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


def build_saved_match_record(match: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "collected_at": utc_iso_now(),
        "source": {
            "name": "deadlock-gg-ui-save",
            "endpoint": "sqlite:matches.raw_json",
        },
        "summary": summarize_saved_match(match),
        "match": match,
    }


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

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.send_error_json("Unknown route", status=404)
            return
        self.handle_api_post(parsed.path)

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
        try:
            if path == "/api/heroes":
                self.send_json(self.api_heroes(params))
                return
            if path == "/api/hero-comparison":
                self.send_json(self.api_hero_comparison(params))
                return
            if path.startswith("/api/heroes/"):
                hero_key = unquote(path.rsplit("/", 1)[-1])
                self.send_json(self.api_hero_detail(hero_key))
                return
        except ValueError as exc:
            self.send_error_json(str(exc), status=404)
            return

        if not self.state.db_path.exists():
            self.send_error_json(f"SQLite database not found: {self.state.db_path}", status=404)
            return
        try:
            if path == "/api/summary":
                self.send_json(self.api_summary())
            elif path == "/api/performances":
                self.send_json(self.api_performances(params))
            elif path == "/api/item-matchups":
                self.send_json(self.api_item_matchups(params))
            elif path == "/api/item-evidence":
                self.send_json(self.api_item_evidence(params))
            elif path.startswith("/api/matches/") and path.endswith("/item-lab"):
                match_id = as_int(path.split("/")[-2], -1)
                self.send_json(self.api_match_item_lab(match_id, params))
            elif path.startswith("/api/matches/") and path.endswith("/ability-sheet"):
                match_id = as_int(path.split("/")[-2], -1)
                self.send_json(self.api_match_ability_sheet(match_id, params))
            elif path.startswith("/api/matches/"):
                match_id = as_int(path.rsplit("/", 1)[-1], -1)
                self.send_json(self.api_match(match_id))
            else:
                self.send_error_json("Unknown API route", status=404)
        except sqlite3.Error as exc:
            self.send_error_json(f"SQLite error: {exc}", status=500)

    def api_heroes(self, params: dict[str, list[str]]) -> dict[str, Any]:
        search = (first(params, "search") or "").strip().lower()
        token = search_token(search)
        heroes = [
            hero_summary_payload(hero, self.state.hero_assets)
            for hero in self.state.raw_hero_assets.values()
            if not hero.get("disabled")
        ]
        if token:
            heroes = [
                hero for hero in heroes
                if token in search_token(hero.get("name"))
                or token in search_token(hero.get("className"))
                or str(hero.get("id")) == search
            ]
        heroes.sort(key=lambda hero: str(hero.get("name") or ""))
        return {"items": heroes, "total": len(heroes)}

    def api_hero_comparison(self, params: dict[str, list[str]]) -> dict[str, Any]:
        search = (first(params, "search") or "").strip()
        search = search_token(search)
        rows = [
            row for row in self.state.hero_comparison_table.get("heroes", [])
            if isinstance(row, dict)
        ]
        if search:
            rows = [
                row for row in rows
                if search in search_token(row.get("hero", {}).get("name"))
                or search in search_token(row.get("values", {}).get("hero"))
                or str(row.get("hero", {}).get("id")) == search
            ]
        return {
            "source": self.state.hero_comparison_table.get("source", {}),
            "counts": self.state.hero_comparison_table.get("counts", {}),
            "columns": self.state.hero_comparison_table.get("columns", []),
            "items": rows,
            "total": len(rows),
        }

    def resolve_hero_asset(self, hero_key: str) -> dict[str, Any]:
        token = search_token(hero_key)
        for hero in self.state.raw_hero_assets.values():
            if str(hero.get("id")) == str(hero_key).strip():
                return hero
            candidates = [
                search_token(hero.get("name")),
                search_token(hero.get("class_name")),
                search_token(str(hero.get("class_name") or "").removeprefix("hero_")),
            ]
            if token and token in candidates:
                return hero
        raise ValueError(f"Hero not found: {hero_key}")

    def api_hero_detail(self, hero_key: str) -> dict[str, Any]:
        hero = self.resolve_hero_asset(hero_key)
        summary = hero_summary_payload(hero, self.state.hero_assets)
        item_refs = hero.get("items") if isinstance(hero.get("items"), dict) else {}
        signature_keys = ["signature1", "signature2", "signature3", "signature4"]
        signatures = [
            normalize_item_asset(
                self.state.raw_item_assets_by_class.get(str(item_refs.get(key) or "")),
                self.state.item_assets,
                self.state.raw_item_assets_by_class,
                True,
            )
            for key in signature_keys
        ]
        weapons = [
            normalize_item_asset(self.state.raw_item_assets_by_class.get(str(item_refs.get(key) or "")), self.state.item_assets)
            for key in ("weapon_primary", "weapon_melee")
        ]
        descriptions = {
            key: text
            for key, value in sorted((hero.get("description") or {}).items())
            if (text := clean_text(value))
        }
        return {
            **summary,
            "colors": hero.get("colors") if isinstance(hero.get("colors"), dict) else {},
            "gunTag": hero.get("gun_tag") or "",
            "description": descriptions,
            "baseStats": group_stats(hero.get("starting_stats")),
            "scalingStats": group_stats(hero.get("scaling_stats")),
            "costBonuses": hero.get("cost_bonuses") if isinstance(hero.get("cost_bonuses"), dict) else {},
            "abilities": [item for item in signatures if item is not None],
            "weapons": [item for item in weapons if item is not None],
            "raw": hero,
        }

    def handle_api_post(self, path: str) -> None:
        if not self.state.db_path.exists():
            self.send_error_json(f"SQLite database not found: {self.state.db_path}", status=404)
            return
        try:
            if path.startswith("/api/matches/") and path.endswith("/save"):
                match_id = as_int(path.split("/")[-2], -1)
                self.send_json(self.api_save_match(match_id))
            else:
                self.send_error_json("Unknown API route", status=404)
        except sqlite3.Error as exc:
            self.send_error_json(f"SQLite error: {exc}", status=500)
        except ValueError as exc:
            self.send_error_json(str(exc), status=404)

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
        enemy_lane_hero = (first(params, "enemyLaneHero") or "").strip().lower()
        saved_only = truthy(first(params, "savedOnly"))
        saved_match_ids = set(load_saved_match_records(self.state.saved_matches_file)) if saved_only else set()

        query = """
            SELECT
              p.match_id, p.player_slot, p.account_id, p.team, p.assigned_lane, p.hero_id, p.hero_name,
              p.kills, p.deaths, p.assists, p.net_worth, p.last_hits, p.denies,
              p.player_level, p.ability_points, p.final_stats_json,
              m.start_time, m.duration_s, m.game_mode, m.match_mode, m.winning_team,
              m.average_badge_team0, m.average_badge_team0_name,
              m.average_badge_team1, m.average_badge_team1_name,
              CASE WHEN m.winning_team = p.team THEN 1 ELSE 0 END AS won
            FROM players p
            JOIN matches m USING(match_id)
        """
        with connect(self.state.db_path) as connection:
            rows = [dict(row) for row in connection.execute(query)]

        lane_players: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for row in rows:
            lane_key = (as_int(row.get("match_id")), as_int(row.get("assigned_lane")))
            lane_players.setdefault(lane_key, []).append(row)

        performances = []
        for row in rows:
            enemy_lane_rows = [
                enemy
                for enemy in lane_players.get((as_int(row.get("match_id")), as_int(row.get("assigned_lane"))), [])
                if enemy.get("team") != row.get("team")
            ]
            if enemy_lane_hero and not any(
                enemy_lane_hero in (enemy.get("hero_name") or "").lower()
                or enemy_lane_hero in str(enemy.get("hero_id"))
                for enemy in enemy_lane_rows
            ):
                continue
            if saved_only and as_int(row.get("match_id")) not in saved_match_ids:
                continue
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
                    "assignedLane": row["assigned_lane"],
                    "enemyLaneHeroes": [
                        {
                            "heroId": enemy.get("hero_id"),
                            "heroName": enemy.get("hero_name"),
                        }
                        for enemy in enemy_lane_rows
                    ],
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
                    "averageBadge": match_badge_payload(row),
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
            "enemyLaneHero": enemy_lane_hero,
            "savedOnly": saved_only,
        }

    def item_matchup_payload(
        self,
        *,
        limit: int,
        min_matches: int,
        hero_token: str,
        item_token: str,
        enemy_tokens: list[str],
        ally_tokens: list[str],
        owned_tokens: list[str],
        exclude_owned_tokens: list[str] | None,
        mode: str,
        enemy_scope: str,
        before_s: int | None,
        min_duration_s: int | None,
        max_duration_s: int | None,
        include_abilities: bool,
        fallback_level: str | None = None,
    ) -> dict[str, Any]:
        if enemy_scope not in {"team", "lane"}:
            enemy_scope = "team"

        with connect(self.state.db_path) as connection:
            player_rows = dict_rows(
                connection.execute(
                    """
                    SELECT
                      p.match_id, p.player_slot, p.hero_id, p.hero_name, p.team, p.assigned_lane,
                      m.duration_s,
                      CASE WHEN m.winning_team = p.team THEN 1 ELSE 0 END AS won
                    FROM players p
                    JOIN matches m USING(match_id)
                    WHERE (? IS NULL OR m.duration_s >= ?)
                      AND (? IS NULL OR m.duration_s <= ?)
                    """,
                    (min_duration_s, min_duration_s, max_duration_s, max_duration_s),
                )
            )
            item_rows = dict_rows(
                connection.execute(
                    """
                    SELECT match_id, player_slot, item_id, item_name, game_time_s, sold_time_s
                    FROM player_items
                    WHERE item_id IS NOT NULL
                      AND game_time_s IS NOT NULL
                    ORDER BY match_id, player_slot, item_id, game_time_s
                    """
                )
            )

        match_players: dict[int, list[dict[str, Any]]] = {}
        for player in player_rows:
            match_players.setdefault(as_int(player.get("match_id")), []).append(player)

        def has_context_hero(player: dict[str, Any], token: str, side: str) -> bool:
            for other in match_players.get(as_int(player.get("match_id")), []):
                same_team = other.get("team") == player.get("team")
                same_player = as_int(other.get("player_slot")) == as_int(player.get("player_slot"))
                if side == "enemy" and same_team:
                    continue
                if side == "ally" and (not same_team or same_player):
                    continue
                if side == "enemy" and enemy_scope == "lane" and as_int(other.get("assigned_lane")) != as_int(player.get("assigned_lane")):
                    continue
                if hero_matches_token(other.get("hero_id"), other.get("hero_name"), token):
                    return True
            return False

        context_players = []
        for player in player_rows:
            if hero_token and not hero_matches_token(player.get("hero_id"), player.get("hero_name"), hero_token):
                continue
            if enemy_tokens and not all(has_context_hero(player, token, "enemy") for token in enemy_tokens):
                continue
            if ally_tokens and not all(has_context_hero(player, token, "ally") for token in ally_tokens):
                continue
            context_players.append(player)

        owned_item_ids: set[int] = set()
        for item_id, asset in self.state.item_assets.items():
            if any(item_matches_token(item_id, asset.get("name"), token) for token in owned_tokens):
                owned_item_ids.add(item_id)
        exclude_owned_item_ids: set[int] = set()
        for item_id, asset in self.state.item_assets.items():
            if any(item_matches_token(item_id, asset.get("name"), token) for token in (exclude_owned_tokens or owned_tokens)):
                exclude_owned_item_ids.add(item_id)

        if owned_item_ids:
            owned_by_context_key: dict[tuple[int, int], set[int]] = {}
            for item in item_rows:
                item_id = as_int(item.get("item_id"))
                if item_id not in owned_item_ids:
                    continue
                buy_time_s = optional_int(item.get("game_time_s"))
                if buy_time_s is None:
                    continue
                if before_s is not None and buy_time_s > before_s:
                    continue
                sold_time_s = optional_int(item.get("sold_time_s"), 1)
                if before_s is not None and sold_time_s is not None and sold_time_s <= before_s:
                    continue
                key = (as_int(item.get("match_id")), as_int(item.get("player_slot")))
                owned_by_context_key.setdefault(key, set()).add(item_id)
            context_players = [
                player for player in context_players
                if owned_item_ids.issubset(owned_by_context_key.get((as_int(player.get("match_id")), as_int(player.get("player_slot"))), set()))
            ]

        baseline_wins = sum(1 for player in context_players if as_int(player.get("won")))
        baseline_total = len(context_players)
        baseline_rate = baseline_wins / baseline_total if baseline_total else 0.0
        if baseline_total < min_matches:
            return {
                "mode": mode,
                "items": [],
                "totalItems": 0,
                "context": {
                    "hero": hero_token,
                    "enemies": enemy_tokens,
                    "allies": ally_tokens,
                    "enemyScope": enemy_scope,
                    "ownedItems": owned_tokens,
                    "beforeS": before_s,
                    "beforeText": mmss(before_s),
                    "minMatches": min_matches,
                    "players": baseline_total,
                    "wins": baseline_wins,
                    "baselineWinRate": round(baseline_rate * 100, 1),
                    "fallbackLevel": fallback_level,
                },
            }

        context_keys = {(as_int(player.get("match_id")), as_int(player.get("player_slot"))) for player in context_players}
        first_buys: dict[tuple[int, int], dict[int, dict[str, Any]]] = {key: {} for key in context_keys}

        for item in item_rows:
            key = (as_int(item.get("match_id")), as_int(item.get("player_slot")))
            if key not in context_keys:
                continue
            item_id = as_int(item.get("item_id"))
            if item_id <= 0:
                continue
            asset = self.state.item_assets.get(item_id, {})
            if asset.get("type") == "ability" and not include_abilities:
                continue
            item_name = asset.get("name") or item.get("item_name") or f"Item {item_id}"
            if item_token and not item_matches_token(item_id, item_name, item_token):
                continue
            if mode == "recommend" and item_id in exclude_owned_item_ids:
                continue
            buy_time_s = as_int(item.get("game_time_s"))
            if before_s is not None and buy_time_s > before_s:
                continue
            current = first_buys[key].get(item_id)
            if current is None or buy_time_s < current["firstBuyS"]:
                first_buys[key][item_id] = {
                    "itemId": item_id,
                    "itemName": item_name,
                    "firstBuyS": buy_time_s,
                    "asset": asset,
                }

        player_wins = {
            (as_int(player.get("match_id")), as_int(player.get("player_slot"))): bool(as_int(player.get("won")))
            for player in context_players
        }

        stats: dict[int, dict[str, Any]] = {}
        for key, buys in first_buys.items():
            for item_id, item in buys.items():
                row = stats.setdefault(
                    item_id,
                    {
                        "itemId": item_id,
                        "itemName": item["itemName"],
                        "asset": item["asset"],
                        "buyers": 0,
                        "wins": 0,
                        "firstBuyTotalS": 0,
                    },
                )
                row["buyers"] += 1
                row["wins"] += 1 if player_wins.get(key) else 0
                row["firstBuyTotalS"] += item["firstBuyS"]

        items = []
        for row in stats.values():
            buyers = as_int(row["buyers"])
            if buyers < min_matches:
                continue
            wins = as_int(row["wins"])
            win_rate = wins / buyers
            low, high = wilson_interval(wins, buyers)
            pick_rate = buyers / baseline_total if baseline_total else 0.0
            lift = win_rate - baseline_rate
            avg_buy_s = row["firstBuyTotalS"] / buyers
            score = lift * 100 + low * 18 + math.log10(buyers + 1)
            items.append(
                {
                    "itemId": row["itemId"],
                    "itemName": row["itemName"],
                    "asset": row["asset"],
                    "buyers": buyers,
                    "wins": wins,
                    "winRate": round(win_rate * 100, 1),
                    "pickRate": round(pick_rate * 100, 1),
                    "lift": round(lift * 100, 1),
                    "wilsonLow": round(low * 100, 1),
                    "wilsonHigh": round(high * 100, 1),
                    "avgBuyS": round(avg_buy_s),
                    "avgBuyText": mmss(avg_buy_s),
                    "score": round(score, 2),
                }
            )

        items.sort(key=lambda item: (item["score"], item["lift"], item["buyers"]), reverse=True)
        return {
            "mode": mode,
            "items": items[:limit],
            "totalItems": len(items),
            "context": {
                "hero": hero_token,
                "enemies": enemy_tokens,
                "allies": ally_tokens,
                "enemyScope": enemy_scope,
                "ownedItems": owned_tokens,
                "beforeS": before_s,
                "beforeText": mmss(before_s),
                "minMatches": min_matches,
                "players": baseline_total,
                "wins": baseline_wins,
                "baselineWinRate": round(baseline_rate * 100, 1),
                "fallbackLevel": fallback_level,
            },
        }

    def api_item_matchups(self, params: dict[str, list[str]]) -> dict[str, Any]:
        return self.item_matchup_payload(
            limit=min(max(as_int(first(params, "limit"), 40), 1), 120),
            min_matches=max(as_int(first(params, "minMatches"), 20), 1),
            hero_token=(first(params, "hero") or "").strip().lower(),
            item_token=(first(params, "item") or "").strip().lower(),
            enemy_tokens=split_tokens(first(params, "enemies") or first(params, "enemy")),
            ally_tokens=split_tokens(first(params, "allies") or first(params, "ally")),
            owned_tokens=split_tokens(first(params, "ownedItems")),
            exclude_owned_tokens=None,
            mode=(first(params, "mode") or "study").strip().lower(),
            enemy_scope=(first(params, "enemyScope") or "team").strip().lower(),
            before_s=optional_int(first(params, "beforeS")),
            min_duration_s=optional_int(first(params, "minDurationS")),
            max_duration_s=optional_int(first(params, "maxDurationS")),
            include_abilities=truthy(first(params, "includeAbilities")),
        )

    def api_item_evidence(self, params: dict[str, list[str]]) -> dict[str, Any]:
        limit = min(max(as_int(first(params, "limit"), 80), 1), 250)
        hero_token = (first(params, "hero") or "").strip().lower()
        item_token = (first(params, "item") or "").strip().lower()
        item_id_filter = optional_int(first(params, "itemId"))
        enemy_tokens = split_tokens(first(params, "enemies") or first(params, "enemy"))
        ally_tokens = split_tokens(first(params, "allies") or first(params, "ally"))
        owned_tokens = split_tokens(first(params, "ownedItems"))
        enemy_scope = (first(params, "enemyScope") or "team").strip().lower()
        if enemy_scope not in {"team", "lane"}:
            enemy_scope = "team"
        before_s = optional_int(first(params, "beforeS"))
        min_duration_s = optional_int(first(params, "minDurationS"))
        max_duration_s = optional_int(first(params, "maxDurationS"))
        include_abilities = truthy(first(params, "includeAbilities"))

        with connect(self.state.db_path) as connection:
            player_rows = dict_rows(
                connection.execute(
                    """
                    SELECT
                      p.match_id, p.player_slot, p.hero_id, p.hero_name, p.team, p.assigned_lane,
                      p.kills, p.deaths, p.assists, p.net_worth, p.final_stats_json,
                      m.start_time, m.duration_s, m.match_mode, m.game_mode,
                      m.average_badge_team0, m.average_badge_team0_name,
                      m.average_badge_team1, m.average_badge_team1_name,
                      CASE WHEN m.winning_team = p.team THEN 1 ELSE 0 END AS won
                    FROM players p
                    JOIN matches m USING(match_id)
                    WHERE (? IS NULL OR m.duration_s >= ?)
                      AND (? IS NULL OR m.duration_s <= ?)
                    """,
                    (min_duration_s, min_duration_s, max_duration_s, max_duration_s),
                )
            )
            item_rows = dict_rows(
                connection.execute(
                    """
                    SELECT match_id, player_slot, item_id, item_name, game_time_s, sold_time_s
                    FROM player_items
                    WHERE item_id IS NOT NULL
                      AND game_time_s IS NOT NULL
                    ORDER BY match_id, player_slot, item_id, game_time_s
                    """
                )
            )

        match_players: dict[int, list[dict[str, Any]]] = {}
        for player in player_rows:
            match_players.setdefault(as_int(player.get("match_id")), []).append(player)

        def matching_enemies(player: dict[str, Any], token: str | None = None) -> list[dict[str, Any]]:
            enemies = []
            for enemy in match_players.get(as_int(player.get("match_id")), []):
                if enemy.get("team") == player.get("team"):
                    continue
                if enemy_scope == "lane" and as_int(enemy.get("assigned_lane")) != as_int(player.get("assigned_lane")):
                    continue
                if token and not hero_matches_token(enemy.get("hero_id"), enemy.get("hero_name"), token):
                    continue
                enemies.append(enemy)
            return enemies

        def matching_allies(player: dict[str, Any], token: str | None = None) -> list[dict[str, Any]]:
            allies = []
            for ally in match_players.get(as_int(player.get("match_id")), []):
                if ally.get("team") != player.get("team"):
                    continue
                if as_int(ally.get("player_slot")) == as_int(player.get("player_slot")):
                    continue
                if token and not hero_matches_token(ally.get("hero_id"), ally.get("hero_name"), token):
                    continue
                allies.append(ally)
            return allies

        context_players = []
        for player in player_rows:
            if hero_token and not hero_matches_token(player.get("hero_id"), player.get("hero_name"), hero_token):
                continue
            if enemy_tokens and not all(matching_enemies(player, token) for token in enemy_tokens):
                continue
            if ally_tokens and not all(matching_allies(player, token) for token in ally_tokens):
                continue
            context_players.append(player)

        owned_item_ids: set[int] = set()
        for owned_item_id, asset in self.state.item_assets.items():
            if any(item_matches_token(owned_item_id, asset.get("name"), token) for token in owned_tokens):
                owned_item_ids.add(owned_item_id)

        if owned_item_ids:
            owned_by_context_key: dict[tuple[int, int], set[int]] = {}
            for item in item_rows:
                item_id = as_int(item.get("item_id"))
                if item_id not in owned_item_ids:
                    continue
                buy_time_s = optional_int(item.get("game_time_s"))
                if buy_time_s is None:
                    continue
                if before_s is not None and buy_time_s > before_s:
                    continue
                sold_time_s = optional_int(item.get("sold_time_s"), 1)
                if before_s is not None and sold_time_s is not None and sold_time_s <= before_s:
                    continue
                key = (as_int(item.get("match_id")), as_int(item.get("player_slot")))
                owned_by_context_key.setdefault(key, set()).add(item_id)
            context_players = [
                player for player in context_players
                if owned_item_ids.issubset(owned_by_context_key.get((as_int(player.get("match_id")), as_int(player.get("player_slot"))), set()))
            ]
        players_by_key = {
            (as_int(player.get("match_id")), as_int(player.get("player_slot"))): player
            for player in context_players
        }

        first_buys: dict[tuple[int, int], dict[str, Any]] = {}
        for item in item_rows:
            key = (as_int(item.get("match_id")), as_int(item.get("player_slot")))
            if key not in players_by_key:
                continue
            item_id = as_int(item.get("item_id"))
            if item_id <= 0:
                continue
            asset = self.state.item_assets.get(item_id, {})
            if asset.get("type") == "ability" and not include_abilities:
                continue
            item_name = asset.get("name") or item.get("item_name") or f"Item {item_id}"
            if item_id_filter is not None and item_id != item_id_filter:
                continue
            if item_token and not item_matches_token(item_id, item_name, item_token):
                continue
            buy_time_s = as_int(item.get("game_time_s"))
            if before_s is not None and buy_time_s > before_s:
                continue
            current = first_buys.get(key)
            if current is None or buy_time_s < current["buyTimeS"]:
                first_buys[key] = {
                    "itemId": item_id,
                    "itemName": item_name,
                    "asset": asset,
                    "buyTimeS": buy_time_s,
                }

        rows = []
        for key, buy in first_buys.items():
            player = players_by_key[key]
            enemies = []
            for token in enemy_tokens:
                enemies.extend(matching_enemies(player, token))
            if not enemy_tokens:
                enemies = matching_enemies(player)
            seen_enemy_slots = set()
            unique_enemies = []
            for enemy in enemies:
                enemy_key = (as_int(enemy.get("match_id")), as_int(enemy.get("player_slot")))
                if enemy_key in seen_enemy_slots:
                    continue
                seen_enemy_slots.add(enemy_key)
                final_stats = json_loads(enemy.get("final_stats_json")) or {}
                unique_enemies.append(
                    {
                        "heroId": enemy.get("hero_id"),
                        "heroName": enemy.get("hero_name"),
                        "playerSlot": enemy.get("player_slot"),
                        "kills": enemy.get("kills"),
                        "deaths": enemy.get("deaths"),
                        "assists": enemy.get("assists"),
                        "netWorth": enemy.get("net_worth"),
                        "playerDamage": final_stats.get("player_damage"),
                    }
                )
            final_stats = json_loads(player.get("final_stats_json")) or {}
            rows.append(
                {
                    "matchId": player.get("match_id"),
                    "playerSlot": player.get("player_slot"),
                    "heroId": player.get("hero_id"),
                    "heroName": player.get("hero_name"),
                    "won": bool(as_int(player.get("won"))),
                    "startTime": player.get("start_time"),
                    "durationS": player.get("duration_s"),
                    "durationText": mmss(player.get("duration_s")),
                    "matchMode": player.get("match_mode"),
                    "gameMode": player.get("game_mode"),
                    "lane": player.get("assigned_lane"),
                    "buyTimeS": buy["buyTimeS"],
                    "buyTimeText": mmss(buy["buyTimeS"]),
                    "itemId": buy["itemId"],
                    "itemName": buy["itemName"],
                    "kills": player.get("kills"),
                    "deaths": player.get("deaths"),
                    "assists": player.get("assists"),
                    "netWorth": player.get("net_worth"),
                    "playerDamage": final_stats.get("player_damage"),
                    "averageBadge": match_badge_payload(player),
                    "enemies": unique_enemies,
                }
            )

        rows.sort(key=lambda row: (not row["won"], row["buyTimeS"], -as_int(row["matchId"])))
        return {
            "items": rows[:limit],
            "totalMatched": len(rows),
            "context": {
                "hero": hero_token,
                "enemies": enemy_tokens,
                "allies": ally_tokens,
                "ownedItems": owned_tokens,
                "enemyScope": enemy_scope,
                "item": item_token,
                "itemId": item_id_filter,
                "beforeS": before_s,
                "beforeText": mmss(before_s),
            },
        }

    def hero_ability_assets(self, hero_id: int) -> list[dict[str, Any]]:
        hero = self.state.raw_hero_assets.get(hero_id)
        if not hero:
            return []
        item_refs = hero.get("items") if isinstance(hero.get("items"), dict) else {}
        abilities = []
        for key in ("signature1", "signature2", "signature3", "signature4"):
            item = self.state.raw_item_assets_by_class.get(str(item_refs.get(key) or ""))
            if not item:
                continue
            abilities.append(item)
            raw_dependents = item.get("dependent_abilities") if isinstance(item.get("dependent_abilities"), dict) else {}
            for class_name, metadata in sorted(raw_dependents.items()):
                flags = metadata.get("flags") if isinstance(metadata, dict) else []
                if "DisplayAsSubAbility" not in flags:
                    continue
                dependent = self.state.raw_item_assets_by_class.get(str(class_name))
                if dependent:
                    abilities.append(dependent)
        return abilities

    def item_is_active_at(self, row: dict[str, Any], time_s: int) -> bool:
        buy_time = optional_int(row.get("game_time_s"))
        if buy_time is None or buy_time > time_s:
            return False
        sell_time = optional_int(row.get("sold_time_s"), 1)
        return sell_time is None or sell_time > time_s

    def api_match_item_lab(self, match_id: int, params: dict[str, list[str]]) -> dict[str, Any]:
        time_s = max(as_int(first(params, "timeS"), 720), 0)
        limit = min(max(as_int(first(params, "limit"), 40), 1), 120)
        min_matches = max(as_int(first(params, "minMatches"), 20), 1)
        include_abilities = truthy(first(params, "includeAbilities"))
        player_slot_filter = optional_int(first(params, "playerSlot"))

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
            item_rows = dict_rows(
                connection.execute(
                    """
                    SELECT *
                    FROM player_items
                    WHERE match_id = ?
                    ORDER BY player_slot, COALESCE(game_time_s, 999999), item_index
                    """,
                    (match_id,),
                )
            )

        if not players:
            return {"error": "No players found for match"}
        player = next(
            (row for row in players if player_slot_filter is not None and as_int(row.get("player_slot")) == player_slot_filter),
            players[0],
        )
        player_slot = as_int(player.get("player_slot"))
        player_team = player.get("team")
        allies = [
            ally for ally in players
            if ally.get("team") == player_team and as_int(ally.get("player_slot")) != player_slot
        ]
        enemies = [enemy for enemy in players if enemy.get("team") != player_team]

        active_items = []
        for item in item_rows:
            if as_int(item.get("player_slot")) != player_slot or not self.item_is_active_at(item, time_s):
                continue
            item_id = as_int(item.get("item_id"))
            if item_id <= 0:
                continue
            asset = self.state.item_assets.get(item_id, {})
            if asset.get("type") == "ability":
                continue
            active_items.append(
                {
                    "itemId": item_id,
                    "itemName": asset.get("name") or item.get("item_name") or f"Item {item_id}",
                    "asset": asset,
                    "buyTimeS": item.get("game_time_s"),
                    "buyTimeText": mmss(item.get("game_time_s")),
                }
            )

        hero_token = str(player.get("hero_name") or player.get("hero_id") or "").lower()
        enemy_tokens = [str(enemy.get("hero_name") or enemy.get("hero_id") or "").lower() for enemy in enemies]
        ally_tokens = [str(ally.get("hero_name") or ally.get("hero_id") or "").lower() for ally in allies]
        owned_tokens = [str(item["itemId"]) for item in active_items]
        attempts = [
            ("Exact", ally_tokens, enemy_tokens, owned_tokens),
            ("Enemies only", [], enemy_tokens, owned_tokens),
            ("Owned only", [], [], owned_tokens),
            ("Hero only", [], [], []),
        ]

        selected_payload: dict[str, Any] | None = None
        for label, attempt_allies, attempt_enemies, attempt_owned in attempts:
            payload = self.item_matchup_payload(
                limit=limit,
                min_matches=min_matches,
                hero_token=hero_token,
                item_token="",
                enemy_tokens=attempt_enemies,
                ally_tokens=attempt_allies,
                owned_tokens=attempt_owned,
                exclude_owned_tokens=owned_tokens,
                mode="recommend",
                enemy_scope="team",
                before_s=time_s,
                min_duration_s=None,
                max_duration_s=None,
                include_abilities=include_abilities,
                fallback_level=label,
            )
            selected_payload = payload
            if as_int(payload.get("context", {}).get("players")) >= min_matches and payload.get("items"):
                break

        selected_payload = selected_payload or {}
        selected_payload["matchContext"] = {
            "matchId": match_id,
            "playerSlot": player_slot,
            "timeS": time_s,
            "timeText": mmss(time_s),
            "hero": {
                "heroId": player.get("hero_id"),
                "heroName": player.get("hero_name"),
                "asset": self.state.hero_assets.get(as_int(player.get("hero_id")), {}),
            },
            "allies": [
                {
                    "heroId": ally.get("hero_id"),
                    "heroName": ally.get("hero_name"),
                    "playerSlot": ally.get("player_slot"),
                    "asset": self.state.hero_assets.get(as_int(ally.get("hero_id")), {}),
                }
                for ally in allies
            ],
            "enemies": [
                {
                    "heroId": enemy.get("hero_id"),
                    "heroName": enemy.get("hero_name"),
                    "playerSlot": enemy.get("player_slot"),
                    "asset": self.state.hero_assets.get(as_int(enemy.get("hero_id")), {}),
                }
                for enemy in enemies
            ],
            "ownedItems": active_items,
        }
        return selected_payload

    def active_sample_at(self, samples: list[dict[str, Any]], time_s: int) -> dict[str, Any]:
        best: dict[str, Any] = {}
        for sample in samples:
            sample_time = optional_int(sample.get("time_stamp_s"))
            if sample_time is not None and sample_time <= time_s:
                best = sample
            elif sample_time is not None and sample_time > time_s:
                break
        return best

    def api_match_ability_sheet(self, match_id: int, params: dict[str, list[str]]) -> dict[str, Any]:
        time_s = max(as_int(first(params, "timeS"), 720), 0)
        include_scaling = truthy(first(params, "includeScaling"))
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

        items_by_player: dict[int, list[dict[str, Any]]] = {}
        samples_by_player: dict[int, list[dict[str, Any]]] = {}
        for item in items:
            items_by_player.setdefault(as_int(item.get("player_slot")), []).append(item)
        for sample in samples:
            raw_sample = json_loads(sample.get("raw_json")) or {}
            if isinstance(raw_sample, dict):
                sample.update({key: value for key, value in raw_sample.items() if key not in sample or sample.get(key) is None})
            sample.pop("raw_json", None)
            samples_by_player.setdefault(as_int(sample.get("player_slot")), []).append(sample)

        rows = []
        for player in players:
            player_slot = as_int(player.get("player_slot"))
            player_items = items_by_player.get(player_slot, [])
            active_items = [
                item for item in player_items
                if self.item_is_active_at(item, time_s)
                and self.state.item_assets.get(as_int(item.get("item_id")), {}).get("type") != "ability"
            ]
            sample = self.active_sample_at(samples_by_player.get(player_slot, []), time_s)
            ability_events: dict[int, list[dict[str, Any]]] = {}
            for item in player_items:
                item_id = as_int(item.get("item_id"))
                asset = self.state.item_assets.get(item_id, {})
                if asset.get("type") != "ability" or not self.item_is_active_at(item, time_s):
                    continue
                ability_events.setdefault(item_id, []).append(item)

            for ability in self.hero_ability_assets(as_int(player.get("hero_id"))):
                ability_id = as_int(ability.get("id"))
                events = ability_events.get(ability_id, [])
                unlocked = bool(events or ability.get("start_trained"))
                rank = max(1, len(events)) if unlocked else 0
                upgrade_tiers = max(0, len(events) - 1)
                normalized = normalize_item_asset(
                    ability,
                    self.state.item_assets,
                    self.state.raw_item_assets_by_class,
                    False,
                ) or {}
                rows.append({
                    "matchId": match_id,
                    "timeS": time_s,
                    "timeText": mmss(time_s),
                    "playerSlot": player_slot,
                    "team": player.get("team"),
                    "heroId": as_int(player.get("hero_id")),
                    "heroName": player.get("hero_name"),
                    "hero": self.state.hero_assets.get(as_int(player.get("hero_id")), {}),
                    "abilityId": ability_id,
                    "abilityName": ability.get("name") or ability.get("class_name"),
                    "ability": normalized,
                    "unlocked": unlocked,
                    "rank": rank,
                    "upgradeTiers": upgrade_tiers,
                    "lastUpgradeText": mmss(max([as_int(event.get("game_time_s")) for event in events], default=0)) if events else "",
                    "damage": ability_metric_value(ability, "damage", upgrade_tiers, sample, include_scaling),
                    "totalDamage": ability_total_damage_value(ability, upgrade_tiers, sample, include_scaling),
                    "cooldown": ability_metric_value(ability, "cooldown", upgrade_tiers, sample, include_scaling),
                    "range": ability_metric_value(ability, "range", upgrade_tiers, sample, include_scaling),
                    "radius": ability_metric_value(ability, "radius", upgrade_tiers, sample, include_scaling),
                    "activeItems": [
                        asset_payload(as_int(item.get("item_id")), self.state.item_assets, "item")
                        for item in active_items
                    ],
                    "sample": {
                        "timeS": sample.get("time_stamp_s"),
                        "timeText": mmss(sample.get("time_stamp_s")),
                        "techPower": sample.get("tech_power"),
                        "weaponPower": sample.get("weapon_power"),
                    } if sample else {},
                })

        return {
            "matchId": match_id,
            "timeS": time_s,
            "timeText": mmss(time_s),
            "includeScaling": include_scaling,
            "columns": ["team", "hero", "player", "ability", "rank", "totalDamage", "cooldown", "range", "radius"],
            "note": "Values include ability upgrades at the selected time. Total Damage uses damage + DPS * the most specific duration field available. Scaling applies known tech-power damage scaling; full item/buff simulation is partial.",
            "rows": rows,
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
        match_payload["averageBadge"] = match_badge_payload(match_payload)
        match_payload["bannedHeroIds"] = json_loads(match_payload.pop("banned_hero_ids_json", None))
        match_payload["objectives"] = json_loads(match_payload.pop("objectives_json", None))
        match_payload["midBoss"] = json_loads(match_payload.pop("mid_boss_json", None))
        match_payload["saved"] = match_id in load_saved_match_records(self.state.saved_matches_file)
        match_payload.pop("raw_json", None)
        return {"match": match_payload, "players": enriched_players}

    def api_save_match(self, match_id: int) -> dict[str, Any]:
        with connect(self.state.db_path) as connection:
            row = connection.execute("SELECT raw_json FROM matches WHERE match_id = ?", (match_id,)).fetchone()
        if row is None or row["raw_json"] is None:
            raise ValueError("Match not found")
        match = json_loads(row["raw_json"])
        if not isinstance(match, dict):
            raise ValueError("Match raw JSON is not available")

        records = load_saved_match_records(self.state.saved_matches_file)
        records[match_id] = build_saved_match_record(match)
        write_saved_match_records(self.state.saved_matches_file, records)
        return {
            "saved": True,
            "matchId": match_id,
            "totalSaved": len(records),
            "output": str(self.state.saved_matches_file),
        }


def first(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    return values[0] if values else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the local Deadlock match detail UI.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--asset-manifest", type=Path, default=DEFAULT_ASSET_MANIFEST)
    parser.add_argument("--hero-comparison-table", type=Path, default=DEFAULT_HERO_COMPARISON_TABLE)
    parser.add_argument("--saved-matches-file", type=Path, default=DEFAULT_SAVED_MATCHES_FILE)
    parser.add_argument("--static-dir", type=Path, default=DEFAULT_STATIC_DIR)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    hero_assets, item_assets, raw_hero_assets, raw_item_assets_by_class, raw_item_assets_by_id = load_assets(args.asset_manifest)
    hero_comparison_table = load_hero_comparison_table(args.hero_comparison_table)
    percentiles, score_count = build_score_percentiles(args.db)
    state = AppState(
        db_path=args.db,
        static_dir=args.static_dir,
        saved_matches_file=args.saved_matches_file,
        hero_comparison_table=hero_comparison_table,
        hero_assets=hero_assets,
        item_assets=item_assets,
        raw_hero_assets=raw_hero_assets,
        raw_item_assets_by_class=raw_item_assets_by_class,
        raw_item_assets_by_id=raw_item_assets_by_id,
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
