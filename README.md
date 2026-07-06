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

Manual one-shot flow:

```sh
cp .env.example .env
./run_deadlock_collector_cycle.sh --dry-run
./run_deadlock_collector_cycle.sh
python scripts/build_deadlock_asset_manifest.py --pretty
python scripts/build_deadlock_sqlite_db.py
```

Output defaults to:

```text
data/deadlock-ranked/
```

See [docs/deadlock-collector.md](docs/deadlock-collector.md) for the API flow, filters, payload shape, and Raspberry Pi deployment.
# deadlock-gg
