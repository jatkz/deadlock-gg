# deadlock-gg

Early Deadlock data collector and match-review UI inspired by the Pi-based Dota collector in `dota-calc-gg`.

The first slice pulls high-skill match metadata from the community Deadlock API, stores append-only JSONL chunks, builds a local SQLite analysis database, and serves a local UI for reviewing standout player performances.

## Quick Start

Turn continuous collection on:

```sh
./deadlock_on
```

Stop continuous collection:

```sh
./deadlock_off
```

Clean generated collector artifacts:

```sh
./deadlock_clean --yes
```

Pull 1000 top-quartile matches and build SQLite:

```sh
./deadlock_pull_1000 --fresh
```

Save specific matches so future fresh pulls keep them:

```sh
./deadlock_save_match 92484329
./deadlock_pull_1000 --fresh
```

Open the local match-detail UI:

```sh
./deadlock_ui
```

Show match duration distribution:

```sh
./deadlock_duration_distribution
```

Show standout performance distribution by hero:

```sh
./deadlock_standout_by_hero
```

Show item win rates for hero/enemy contexts:

```sh
./deadlock_item_matchups --hero Wraith --enemy Dynamo --enemy-scope lane --before-minutes 12 --min-matches 5
```

Run the replay/demo query spike for a specific match:

```sh
./deadlock_demo_query schema --match-id 92525538
./deadlock_demo_query run --match-id 92525538 --print-query
./deadlock_demo_query run --match-id 92525538
```

Manual one-shot flow:

```sh
cp .env.example .env
./run_deadlock_collector_cycle.sh --dry-run
./run_deadlock_collector_cycle.sh
python scripts/build_deadlock_asset_manifest.py --pretty
python scripts/build_deadlock_sqlite_db.py
```

Pull the Deadlock wiki hero comparison table into local JSON/CSV:

```sh
./deadlock_hero_comparison_table --pretty
```

If `deadlock.wiki` returns a browser challenge, save the rendered page HTML from your browser and build from that file:

```sh
./deadlock_hero_comparison_table --source-file ~/Downloads/Hero_Comparison_Table.html --pretty
```

Pull Deadlock wiki item pages, including sectioned interaction tables and item/hero links:

```sh
./deadlock_item_pages --pretty
./deadlock_item_pages --item "Crippling Headshot" --pretty
```

Output defaults to:

```text
data/deadlock-ranked/
```

Saved matches are stored separately in:

```text
data/deadlock-saved/saved_matches.jsonl
```

See [docs/deadlock-collector.md](docs/deadlock-collector.md) for the API flow, filters, payload shape, and Raspberry Pi deployment.
# deadlock-gg


## Damage Calculator

Start `./deadlock_ui`, then choose **Damage Calculator** or open `/damage.html` on the same server. Restart an already running server to load the new `/api/damage-data` endpoint. The calculator needs the asset manifest but does not require a match database.

Choose a hero, boons earned (zero means the starting state), owned items, and each ability's upgrade tier. AP is shown as cumulative spending: 0, 1, 3, or 8 points. Allocations beyond the available AP or ability unlocks are labeled as sandbox configurations. Builds and target settings are saved in browser local storage.

Enter target health, barrier, final combined resistances, and final combined resist reductions. Bullet results include body/head damage per bullet, damage per shot with all pellets hitting, and DPS while firing. Falloff retention and the final headshot multiplier are explicit inputs; the default headshot multiplier is a scenario value, not a verified value for every hero. Ability results evaluate a selected component for a chosen number of hits, ticks, or seconds of exposure. Each result starts with a fresh target, so barriers are not consumed across results.

Accuracy is limited to the displayed snapshot and supported formulas:
- Hero bullet growth, supported bullet spirit scaling, additive spirit scaling, and numeric ability upgrades are evaluated from cached assets.
- Items automatically contribute unconditional spirit, spirit percentage, weapon damage, fire rate, health, melee damage, and category investment bonuses. Legacy tier purchase bonuses are not counted on top of investment.
- Conditional item effects and procs are not simulated. The page lists unapplied properties and provides inputs for extra stats, amplification, resistance reduction, and an exact spirit override.
- Linked abilities, special scaling, health-based damage, alternate fire, reload cycles, and combat sequences require additional formulas. Unsupported components have no numerical result. Component damage should not be interpreted as complete cast damage.
- The snapshot date is shown on the page. Refresh assets with `python scripts/build_deadlock_asset_manifest.py --pretty` and restart the server when needed; patch-specific formulas still need verification against the game.

Verification:

```sh
node --test tests/damage.test.mjs
python -m py_compile scripts/deadlock_match_ui_server.py
# With Playwright installed and a UI server on port 8766:
node tests/damage.browser.cjs
# Optional arguments: path to Playwright package, then server base URL.
```

The Attacker panel shows maximum health and light/heavy melee damage before target defenses. These update with boons, supported item bonuses, weapon bonuses, and supported hero spirit scaling. Maximum health is rounded up for display. Ability-granted stat bonuses and conditional melee procs are not automatically included.

Use **Browse Inventory** in the Items section for a modal grouped by Weapon, Vitality, and Spirit, then by tier and soul cost. Search and tier/type filters narrow the selection; click items to equip or remove them while the modal stays open. Changes apply immediately. Close with Done, Close, Escape, or a click outside the modal. The inline quick search remains available.

Items retain their order of addition in **Build order**, with cumulative soul cost and arrows to move purchases earlier or later. Click an item, use Previous/Next, or move the build-step slider to preview only the items purchased through that step. Step 0 previews an empty inventory. Later items remain saved. **Return to full build** restores every item immediately. Previewing changes only the active items; boons, AP, and target settings stay as entered. Inventory edits exit preview mode. Order is saved across reloads; the temporary preview is not.
