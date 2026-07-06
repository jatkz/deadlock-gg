# Deadlock Match Collector

The collector pulls high-skill Deadlock match metadata from:

```text
https://api.deadlock-api.com/v1/matches/metadata
```

It writes append-only records under `DEADLOCK_DATA_DIR`, defaulting to:

```text
data/deadlock-ranked
```

Each output file is date-partitioned JSONL, compressed by default:

```text
deadlock_matches_2026-07-06_part0001.jsonl.gz
```

The state file lives beside the chunks:

```text
deadlock_match_collector_state.json
```

It tracks seen match IDs, output chunk position, total saved matches, latest run status, and the backfill cursor.

## Pull Strategy

Default mode is `DEADLOCK_SCAN_MODE=newest`. Each cycle requests the newest page matching the configured filters, saves unseen match IDs, and exits. This is simple and robust for a timer because repeated pages are deduped by local state.

For historical collection, set:

```sh
DEADLOCK_SCAN_MODE=backfill
DEADLOCK_MAX_REQUESTS_PER_RUN=5
```

Backfill mode orders by `match_id desc` and moves `max_match_id` backward after each page.

The default metadata pull includes player items, stat samples, final stats, and death details. Death details provide exact death timestamps, killer player slots, death duration, time-to-kill, and death/killer positions for the local UI death timeline.

## High-Skill Filter

The main rank filter is:

```sh
DEADLOCK_MIN_AVERAGE_BADGE=84
```

Deadlock badges are encoded as tier/subtier. The first digits are tier and the final digit is the subtier. Current rank tiers run through `11`:

```text
80+  Oracle-ish and above
90+  Phantom-ish and above
84+  stricter side of the current top quartile
100+ Ascendant-ish and above
110+ Eternus-ish and above
116  Eternus 6
```

The default filter is intentionally strict:

```sh
DEADLOCK_GAME_MODE=normal
DEADLOCK_MIN_AVERAGE_BADGE=84
DEADLOCK_MIN_DURATION_SECONDS=720
```

As of the July 6, 2026 distribution sampled from `/v1/analytics/game-stats?bucket=avg_badge&game_mode=normal&min_duration_s=900`, `83+` was about 26.36% of matches and `84+` was about 23.99%, so `84` is the default for a strict top-quartile pull. The default duration gate is now 12 minutes to keep more legitimate games while still excluding very short outliers.

You can also try:

```sh
DEADLOCK_IS_HIGH_SKILL_RANGE_PARTIES=true
DEADLOCK_MATCH_MODE=ranked
```

Leave `DEADLOCK_MATCH_MODE` unset until you confirm the current API enum values you want to keep.

## Returned Data

The collector requests:

```text
include_info=true
include_objectives=true
include_mid_boss=true
include_player_info=true
include_player_kda=true
include_player_items=true
include_player_stats=true
include_player_final_stats=true
```

Saved records are envelopes:

```json
{
  "schema_version": 1,
  "collected_at": "2026-07-06T15:00:00Z",
  "source": {
    "name": "deadlock-api",
    "endpoint": "/v1/matches/metadata",
    "query": {}
  },
  "summary": {
    "match_id": 92497671,
    "duration_s": 2238,
    "average_badge_team0": 115,
    "average_badge_team1": 115,
    "player_count": 12,
    "hero_ids": []
  },
  "match": {}
}
```

The raw `match` object normally includes match-level fields such as:

```text
match_id
start_time
duration_s
game_mode
match_mode
winning_team
match_outcome
average_badge_team0
average_badge_team1
banned_hero_ids
objectives
mid_boss
players
```

Each player can include:

```text
account_id
hero_id
hero_build_id
team
player_slot
assigned_lane
kills
deaths
assists
net_worth
last_hits
denies
player_level
ability_points
items
stats
final_stats
accolades
abandon_match_time_s
```

Set `DEADLOCK_SAVE_RAW_MATCH=false` if you only want summaries.

## Local Cycle

Continuous local or Pi collection:

```sh
./deadlock_on
```

Stop the timer and service:

```sh
./deadlock_off
```

Remove generated data, analysis DBs, package archives, and Python caches:

```sh
./deadlock_clean --yes
```

Pull up to 1000 top-quartile matches and build SQLite:

```sh
./deadlock_pull_1000
```

Use `./deadlock_pull_1000 --fresh` to remove existing raw match chunks and analysis DBs first.

Manual one-shot collection:

```sh
cp .env.example .env
./run_deadlock_collector_cycle.sh --dry-run
./run_deadlock_collector_cycle.sh
python scripts/build_deadlock_asset_manifest.py --pretty
python scripts/build_deadlock_sqlite_db.py
```

`--dry-run` fetches a page and prints summaries without writing chunks or state.

Progress logging is enabled by default with `DEADLOCK_LOG_LEVEL=info`. Backfill runs print one line per requested page:

```text
[2026-07-06T15:00:00Z] page 1/20 fetched=100 saved=100 total_saved_this_run=100 saved_total=100 cursor=92490000 elapsed_s=3.2
```

Set `DEADLOCK_LOG_LEVEL=quiet` to suppress progress logs.

The asset manifest caches `/v1/assets/heroes`, `/v1/assets/items`, and `/v1/assets/ranks` to:

```text
assets/deadlock/manifest.json
```

The SQLite builder reads JSONL chunks and creates:

```text
data/deadlock-analysis/deadlock_matches.sqlite
```

The first schema includes `matches`, `players`, `player_items`, and `player_stat_samples`.

## Raspberry Pi Deployment

Create the archive on your main machine:

```sh
./package_deadlock_collector_for_pi.sh
```

Include your local `.env`:

```sh
./package_deadlock_collector_for_pi.sh --with-env
```

Copy it to the Pi:

```sh
scp collector-dist/deadlock_collector_pi.tar.gz pi@raspberrypi.local:~
```

On the Pi:

```sh
mkdir -p ~/deadlock_gg_collector
tar -xzf ~/deadlock_collector_pi.tar.gz -C ~/deadlock_gg_collector
cd ~/deadlock_gg_collector
./deploy/deadlock-collector/install_on_pi.sh
./run_deadlock_collector_cycle.sh --dry-run
./deadlock_on
```

Useful checks:

```sh
sudo systemctl status deadlock-match-collector.timer
sudo systemctl list-timers --all | grep deadlock-match-collector
sudo journalctl -u deadlock-match-collector.service -n 100 --no-pager
```

## Pull Data Back

From the main machine:

```sh
./pull_deadlock_data_from_pi.sh pi@raspberrypi.local
```

Or set these in `.env`:

```sh
DEADLOCK_PI_SSH=pi@raspberrypi.local
DEADLOCK_PI_REMOTE_DATA_DIR=~/deadlock_gg_collector/data/deadlock-ranked
DEADLOCK_PI_LOCAL_DATA_DIR=data/deadlock-ranked-pi
```

Then run:

```sh
./pull_deadlock_data_from_pi.sh
```
