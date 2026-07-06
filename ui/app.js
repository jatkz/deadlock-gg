const state = {
  performances: [],
  selectedPerformance: null,
  selectedMatch: null,
  selectedPlayerSlot: null,
  metric: "player_damage",
};

const el = {
  datasetSummary: document.querySelector("#datasetSummary"),
  availability: document.querySelector("#availability"),
  percentileInput: document.querySelector("#percentileInput"),
  percentileValue: document.querySelector("#percentileValue"),
  minDurationInput: document.querySelector("#minDurationInput"),
  maxDurationInput: document.querySelector("#maxDurationInput"),
  minKdaInput: document.querySelector("#minKdaInput"),
  searchInput: document.querySelector("#searchInput"),
  refreshButton: document.querySelector("#refreshButton"),
  performanceList: document.querySelector("#performanceList"),
  resultCount: document.querySelector("#resultCount"),
  emptyState: document.querySelector("#emptyState"),
  matchDetail: document.querySelector("#matchDetail"),
  featuredHeroCard: document.querySelector("#featuredHeroCard"),
  matchMeta: document.querySelector("#matchMeta"),
  featuredTitle: document.querySelector("#featuredTitle"),
  featuredStats: document.querySelector("#featuredStats"),
  scoreboard: document.querySelector("#scoreboard"),
  scoreNote: document.querySelector("#scoreNote"),
  routeTitle: document.querySelector("#routeTitle"),
  routeSubtitle: document.querySelector("#routeSubtitle"),
  itemRoute: document.querySelector("#itemRoute"),
  abilitySubtitle: document.querySelector("#abilitySubtitle"),
  abilityRoute: document.querySelector("#abilityRoute"),
  timelineChart: document.querySelector("#timelineChart"),
  combatTimeline: document.querySelector("#combatTimeline"),
  killDeathTimeline: document.querySelector("#killDeathTimeline"),
  finalStats: document.querySelector("#finalStats"),
  finalStatsNote: document.querySelector("#finalStatsNote"),
};

const metricLabels = {
  player_damage: "Player damage",
  net_worth: "Net worth",
  kills: "Kills",
  assists: "Assists",
  farm_kills: "Farm",
  ability_points: "Ability points earned",
  player_damage_taken: "Damage taken",
};

const FILTER_STORAGE_KEY = "deadlockMatchUiFilters";

function fmt(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toLocaleString();
}

function pct(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

function mmss(seconds) {
  const safe = Math.max(0, Number(seconds || 0));
  const minutes = Math.floor(safe / 60);
  const secs = String(Math.floor(safe % 60)).padStart(2, "0");
  return `${minutes}:${secs}`;
}

function durationRangeText(range) {
  if (!range || range.min_duration_s === null || range.max_duration_s === null) return "";
  return ` · durations ${mmss(range.min_duration_s)}-${mmss(range.max_duration_s)}`;
}

function minuteInputToSeconds(input) {
  const raw = input.value.trim();
  if (!raw) return "";
  const minutes = Number(raw);
  if (!Number.isFinite(minutes) || minutes < 0) return "";
  return String(Math.round(minutes * 60));
}

function numericInputValue(input) {
  const raw = input.value.trim();
  if (!raw) return "";
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) return "";
  return String(value);
}

function currentFilters() {
  return {
    minPercentile: el.percentileInput.value,
    minDuration: el.minDurationInput.value,
    maxDuration: el.maxDurationInput.value,
    minKda: el.minKdaInput.value,
    search: el.searchInput.value,
  };
}

function applyFilters(filters) {
  if (!filters || typeof filters !== "object") return;
  if (filters.minPercentile !== undefined) {
    const value = Number(filters.minPercentile);
    if (Number.isFinite(value)) {
      el.percentileInput.value = String(Math.min(99, Math.max(80, Math.round(value))));
    }
  }
  if (filters.minDuration !== undefined) el.minDurationInput.value = String(filters.minDuration);
  if (filters.maxDuration !== undefined) el.maxDurationInput.value = String(filters.maxDuration);
  if (filters.minKda !== undefined) el.minKdaInput.value = String(filters.minKda);
  if (filters.search !== undefined) el.searchInput.value = String(filters.search);
  el.percentileValue.textContent = el.percentileInput.value;
}

function loadSavedFilters() {
  try {
    applyFilters(JSON.parse(localStorage.getItem(FILTER_STORAGE_KEY)));
  } catch (_error) {
    try {
      localStorage.removeItem(FILTER_STORAGE_KEY);
    } catch (_ignored) {
      // Ignore storage failures; filters still work for the current page.
    }
  }
}

function saveFilters() {
  try {
    localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(currentFilters()));
  } catch (_error) {
    // Ignore storage failures; filters still work for the current page.
  }
}

function saveFiltersAndLoadPerformances() {
  saveFilters();
  return loadPerformances();
}

async function getJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

async function loadSummary() {
  const summary = await getJson("/api/summary");
  const counts = summary.counts;
  el.datasetSummary.textContent = `${fmt(counts.matches)} matches, ${fmt(counts.players)} players, ${fmt(counts.items)} item buys, ${fmt(counts.statSamples)} stat samples${durationRangeText(summary.range)}`;
  el.availability.innerHTML = `
    <div><strong>Ready:</strong> shop item route, ability order, final stats, cumulative timelines, kill/death timelines when collected.</div>
    <div><strong>Bias note:</strong> raw standout score favors longer games because it uses cumulative totals. Use duration filters for fairer comparisons.</div>
    <div><strong>Missing:</strong> attack targets are not in the current metadata pull.</div>
    <div><strong>Next data layer:</strong> demo query extraction for target-specific combat events.</div>
  `;
}

async function loadPerformances() {
  const params = new URLSearchParams({
    minPercentile: el.percentileInput.value,
    search: el.searchInput.value.trim(),
    limit: "80",
  });
  const minDurationS = minuteInputToSeconds(el.minDurationInput);
  const maxDurationS = minuteInputToSeconds(el.maxDurationInput);
  const minKda = numericInputValue(el.minKdaInput);
  if (minDurationS) params.set("minDurationS", minDurationS);
  if (maxDurationS) params.set("maxDurationS", maxDurationS);
  if (minKda) params.set("minKda", minKda);
  const payload = await getJson(`/api/performances?${params.toString()}`);
  state.performances = payload.items;
  el.resultCount.textContent = `${fmt(payload.totalMatched)} found`;
  renderPerformanceList();
  if (!state.selectedPerformance && state.performances.length) {
    await selectPerformance(state.performances[0]);
  }
}

function renderPerformanceList() {
  el.performanceList.innerHTML = "";
  for (const perf of state.performances) {
    const button = document.createElement("button");
    button.className = "performanceCard";
    if (
      state.selectedPerformance &&
      state.selectedPerformance.matchId === perf.matchId &&
      state.selectedPerformance.playerSlot === perf.playerSlot
    ) {
      button.classList.add("active");
    }
    button.innerHTML = `
      <img class="heroIcon" src="${perf.hero?.icon || ""}" alt="">
      <span class="perfMain">
        <strong>${perf.heroName || "Unknown hero"}</strong>
        <span class="meta">Match ${perf.matchId} · ${perf.durationText} · <span class="${perf.won ? "win" : "loss"}">${perf.won ? "Win" : "Loss"}</span></span>
        <span class="meta">${fmt(perf.kills)}/${fmt(perf.deaths)}/${fmt(perf.assists)} · ${fmt(perf.kdaRatio)} KDA · ${fmt(perf.netWorth)} NW · ${fmt(perf.playerDamage)} dmg</span>
        <span class="reasonTags">${(perf.reasons || []).map((reason) => `<span class="reasonTag">${reason}</span>`).join("")}</span>
      </span>
      <span class="perfScore">
        <strong>${pct(perf.percentile)}</strong>
        <span class="meta">${fmt(perf.score)}</span>
      </span>
    `;
    button.addEventListener("click", () => selectPerformance(perf));
    el.performanceList.appendChild(button);
  }
}

async function selectPerformance(perf) {
  state.selectedPerformance = perf;
  state.selectedPlayerSlot = perf.playerSlot;
  state.selectedMatch = await getJson(`/api/matches/${perf.matchId}`);
  renderPerformanceList();
  renderMatch();
}

function selectedPlayer() {
  if (!state.selectedMatch) return null;
  return state.selectedMatch.players.find((player) => Number(player.player_slot) === Number(state.selectedPlayerSlot));
}

function renderMatch() {
  const payload = state.selectedMatch;
  if (!payload || !payload.match) return;
  const match = payload.match;
  const player = selectedPlayer() || payload.players[0];
  state.selectedPlayerSlot = player.player_slot;

  el.emptyState.classList.add("hidden");
  el.matchDetail.classList.remove("hidden");
  el.featuredHeroCard.src = player.hero?.card || player.hero?.icon || "";
  el.matchMeta.textContent = `Match ${match.match_id} · ${match.start_time || "unknown start"} · ${match.durationText} · ${match.game_mode || ""} ${match.match_mode || ""}`;
  el.featuredTitle.textContent = `${player.hero_name || "Unknown hero"} standout performance`;
  el.featuredStats.innerHTML = [
    ["Score", fmt(player.score)],
    ["Percentile", pct(player.percentile)],
    ["K/D/A", `${fmt(player.kills)}/${fmt(player.deaths)}/${fmt(player.assists)}`],
    ["KDA ratio", fmt(player.kdaRatio)],
    ["Net worth", fmt(player.net_worth)],
    ["Damage", fmt(player.finalStats?.player_damage)],
    ["Result", player.won ? "Win" : "Loss"],
    ["Why", (player.reasons || []).join(", ") || "strong score"],
  ].map(([label, value]) => `<span class="pill">${label}: <strong>${value}</strong></span>`).join("");

  renderScoreboard(payload.players);
  renderSelectedPlayer(player);
}

function renderScoreboard(players) {
  el.scoreNote.textContent = "Click a player to inspect their route";
  el.scoreboard.innerHTML = "";

  const sortedTeams = ["Team0", "Team1"];
  const grouped = players.reduce((groups, player) => {
    const team = player.team || "Unknown";
    if (!groups.has(team)) groups.set(team, []);
    groups.get(team).push(player);
    return groups;
  }, new Map());
  for (const team of grouped.keys()) {
    if (!sortedTeams.includes(team)) sortedTeams.push(team);
  }

  for (const team of sortedTeams) {
    const teamPlayers = grouped.get(team) || [];
    const column = document.createElement("div");
    column.className = "teamColumn";
    column.innerHTML = `
      <div class="teamHeader">
        <span>${team === "Team0" ? "Team 0" : team === "Team1" ? "Team 1" : team}</span>
        <span>${teamPlayers.length} players</span>
      </div>
    `;

    for (const player of teamPlayers.slice().sort((a, b) => Number(b.score) - Number(a.score))) {
      column.appendChild(renderPlayerRow(player));
    }

    el.scoreboard.appendChild(column);
  }
}

function renderPlayerRow(player) {
  const button = document.createElement("button");
  button.className = "playerRow";
  if (Number(player.player_slot) === Number(state.selectedPlayerSlot)) button.classList.add("active");
  button.innerHTML = `
    <img src="${player.hero?.icon || ""}" alt="">
    <span>
      <strong>${player.hero_name || "Unknown hero"}</strong>
      <span class="meta">${player.team || "team"} · ${fmt(player.kills)}/${fmt(player.deaths)}/${fmt(player.assists)} · ${fmt(player.net_worth)} NW</span>
    </span>
    <span class="perfScore">
      <strong>${pct(player.percentile)}</strong>
      <span class="meta">${fmt(player.score)}</span>
    </span>
  `;
  button.addEventListener("click", () => {
    state.selectedPlayerSlot = player.player_slot;
    renderMatch();
  });
  return button;
}

function renderSelectedPlayer(player) {
  const abilityItems = (player.items || []).filter((item) => item.itemKind === "ability" || item.asset?.type === "ability");
  const shopItems = (player.items || []).filter((item) => !(item.itemKind === "ability" || item.asset?.type === "ability"));

  el.routeTitle.textContent = `${player.hero_name || "Hero"} shop items`;
  el.routeSubtitle.textContent = `${shopItems.length} purchases`;
  el.itemRoute.innerHTML = shopItems.length
    ? shopItems.map(renderShopItem).join("")
    : `<p class="subtle">No shop item purchases were stored for this player.</p>`;

  el.abilitySubtitle.textContent = `${abilityItems.length} events`;
  el.abilityRoute.innerHTML = abilityItems.length
    ? abilityItems.map(renderAbilityItem).join("")
    : `<p class="subtle">No ability order rows were stored for this player.</p>`;

  renderChart(player);
  renderCombatTimeline(player);
  renderKillDeathTimeline(player);
  renderFinalStats(player);
}

function renderNetWorthEstimate(label, estimate) {
  if (!estimate || estimate.value === null || estimate.value === undefined) return "";
  const sampleTime = estimate.timeText ? ` @ ${estimate.timeText}` : "";
  return `<span>${label} ~${fmt(estimate.value)} NW${sampleTime}</span>`;
}

function shopItemTypeClass(item) {
  const slot = String(item.asset?.slot || item.asset?.type || "").toLowerCase();
  if (slot.includes("weapon")) return "weaponItem";
  if (slot.includes("vitality")) return "vitalityItem";
  if (slot.includes("spirit")) return "spiritItem";
  return "";
}

function renderShopItem(item) {
  const netWorthLines = [
    renderNetWorthEstimate("buy", item.estimatedNetWorthAtBuy),
    item.sold_time_s ? renderNetWorthEstimate("sell", item.estimatedNetWorthAtSell) : "",
  ].filter(Boolean).join("");
  const itemMeta = [
    item.asset?.slot || item.asset?.type || "shop",
    item.imbuedAbility ? `imbued: ${item.imbuedAbility.name}` : "",
    item.sold_time_s ? `sold ${mmss(item.sold_time_s)}` : "",
  ].filter(Boolean).join(" · ");
  return `
    <div class="itemBuy ${shopItemTypeClass(item)}">
      <span class="meta">${item.timeText || mmss(item.game_time_s)}</span>
      <img src="${item.asset?.image || ""}" alt="">
      <span>
        <strong>${item.item_name || item.asset?.name || item.item_id || "Unknown item"}</strong>
        <span class="meta">${itemMeta}</span>
      </span>
      <span class="meta nwEstimate">${netWorthLines || "-"}</span>
    </div>
  `;
}

function renderAbilityItem(item) {
  const step = item.abilityStep || (Number(item.upgrade_id || 0) === 0 ? "unlock" : "upgrade");
  return `
    <div class="itemBuy abilityBuy">
      <span class="meta">${item.timeText || mmss(item.game_time_s)}</span>
      <img src="${item.asset?.image || ""}" alt="">
      <span>
        <strong>${item.item_name || item.asset?.name || item.item_id || "Unknown ability"}</strong>
        <span class="meta">${step}${item.upgrade_id ? ` · upgrade ${item.upgrade_id}` : ""}</span>
      </span>
      <span class="abilityStep ${step}">${step}</span>
    </div>
  `;
}

function chartSeries(metric) {
  if (metric === "farm_kills") {
    return [
      { key: "creep_kills", label: "Lane creeps", color: "#d8c35b", pointColor: "#efe08a" },
      { key: "neutral_kills", label: "Neutrals", color: "#70c6aa", pointColor: "#9be5cc" },
    ];
  }
  return [
    { key: metric, label: metricLabels[metric] || metric, color: "#d8c35b", pointColor: "#70c6aa" },
  ];
}

function renderChart(player) {
  const samples = player.stats || [];
  if (!samples.length) {
    el.timelineChart.innerHTML = `<p class="emptyState">No timeline samples for this player.</p>`;
    return;
  }

  const metric = state.metric;
  const series = chartSeries(metric).map((item) => ({
    ...item,
    points: samples
      .map((sample) => ({
        sample,
        x: Number(sample.time_stamp_s || 0),
        y: Number(sample[item.key] || 0),
      }))
      .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y)),
  }));
  const allPoints = series.flatMap((item) => item.points);
  const maxX = Math.max(...allPoints.map((point) => point.x), 1);
  const maxY = Math.max(...allPoints.map((point) => point.y), 1);
  const width = 760;
  const height = 330;
  const pad = { left: 56, right: 24, top: 24, bottom: 44 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const coord = (point) => {
    const x = pad.left + (point.x / maxX) * plotW;
    const y = pad.top + plotH - (point.y / maxY) * plotH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  };
  const lines = series.map((item) => `
    <polyline points="${item.points.map(coord).join(" ")}" fill="none" stroke="${item.color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
  `).join("");
  const circles = series.map((item) => `
    <g fill="${item.pointColor}">
      ${item.points.map((point) => {
        const [x, y] = coord(point).split(",");
        return `<circle cx="${x}" cy="${y}" r="3"><title>${mmss(point.sample.time_stamp_s)} · ${item.label}: ${fmt(point.y)}</title></circle>`;
      }).join("")}
    </g>
  `).join("");
  const legend = series.length > 1 ? series.map((item, index) => {
    const x = pad.left + index * 122;
    return `
      <g>
        <line x1="${x}" y1="${height - 23}" x2="${x + 20}" y2="${height - 23}" stroke="${item.color}" stroke-width="3" stroke-linecap="round"></line>
        <text x="${x + 28}" y="${height - 19}" class="axisText">${item.label}</text>
      </g>
    `;
  }).join("") : "";

  el.timelineChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${metricLabels[metric]} timeline">
      <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${pad.top + plotH}" stroke="#343b2f"></line>
      <line x1="${pad.left}" y1="${pad.top + plotH}" x2="${pad.left + plotW}" y2="${pad.top + plotH}" stroke="#343b2f"></line>
      <text x="${pad.left}" y="18" class="axisText">${metricLabels[metric]}</text>
      <text x="${pad.left}" y="${height - 12}" class="axisText">0:00</text>
      <text x="${pad.left + plotW - 42}" y="${height - 12}" class="axisText">${mmss(maxX)}</text>
      <text x="8" y="${pad.top + 8}" class="axisText">${fmt(maxY)}</text>
      ${lines}
      ${circles}
      ${legend}
    </svg>
  `;
}

function statDelta(current, previous, key) {
  return Math.max(0, Number(current?.[key] || 0) - Number(previous?.[key] || 0));
}

function deltaChip(label, value, suffix = "") {
  if (!value) return "";
  return `<span class="deltaChip">${label} +${fmt(value)}${suffix}</span>`;
}

function renderCombatTimeline(player) {
  const samples = player.stats || [];
  if (samples.length < 2) {
    el.combatTimeline.innerHTML = `<p class="subtle">No sample intervals for this player.</p>`;
    return;
  }

  const rows = [];
  for (let index = 1; index < samples.length; index += 1) {
    const previous = samples[index - 1];
    const current = samples[index];
    const chips = [
      deltaChip("kills", statDelta(current, previous, "kills")),
      deltaChip("deaths", statDelta(current, previous, "deaths")),
      deltaChip("assists", statDelta(current, previous, "assists")),
      deltaChip("damage", statDelta(current, previous, "player_damage")),
      deltaChip("taken", statDelta(current, previous, "player_damage_taken")),
      deltaChip("healing", statDelta(current, previous, "player_healing")),
      deltaChip("ability kills", statDelta(current, previous, "ability_kills")),
      deltaChip("bullet kills", statDelta(current, previous, "bullet_kills")),
      deltaChip("melee kills", statDelta(current, previous, "melee_kills")),
      deltaChip("headshots", statDelta(current, previous, "headshot_kills")),
    ].filter(Boolean);
    if (!chips.length) continue;
    rows.push(`
      <div class="combatEvent">
        <span class="combatTime">${previous.timeText || mmss(previous.time_stamp_s)}-${current.timeText || mmss(current.time_stamp_s)}</span>
        <span class="combatDeltas">${chips.join("")}</span>
      </div>
    `);
  }

  el.combatTimeline.innerHTML = rows.length
    ? rows.join("")
    : `<p class="subtle">No combat deltas in the stored samples.</p>`;
}

function playerBySlot(slot) {
  if (!state.selectedMatch) return null;
  return state.selectedMatch.players.find((player) => Number(player.player_slot) === Number(slot)) || null;
}

function renderKillDeathTimeline(player) {
  const selectedSlot = Number(player.player_slot);
  const allDeathDetails = (state.selectedMatch?.players || []).flatMap((victim) => (
    (victim.deathDetails || []).map((detail) => ({ detail, victim }))
  ));
  if (!allDeathDetails.length) {
    el.killDeathTimeline.innerHTML = `<p class="subtle">No exact death details stored for this match. New pulls with death details enabled will populate this.</p>`;
    return;
  }

  const events = allDeathDetails.flatMap(({ detail, victim }) => {
    const eventTime = Number(detail.game_time_s || 0);
    const timeToKill = Number.isFinite(Number(detail.time_to_kill_s)) ? `${Number(detail.time_to_kill_s).toFixed(1)}s TTK` : "";
    const deathDuration = Number.isFinite(Number(detail.death_duration_s)) ? `${fmt(detail.death_duration_s)}s death` : "";
    const victimDeathDuration = Number.isFinite(Number(detail.death_duration_s)) ? `${fmt(detail.death_duration_s)}s victim death` : "";
    if (Number(victim.player_slot) === selectedSlot) {
      const killer = playerBySlot(detail.killer_player_slot);
      const killerLabel = killer ? killer.hero_name || `slot ${detail.killer_player_slot}` : `slot ${detail.killer_player_slot}`;
      return [{
        type: "death",
        time: eventTime,
        chips: [
          `<span class="deltaChip">died to ${killerLabel}</span>`,
          timeToKill ? `<span class="deltaChip">${timeToKill}</span>` : "",
          deathDuration ? `<span class="deltaChip">${deathDuration}</span>` : "",
        ].filter(Boolean).join(""),
      }];
    }
    if (Number(detail.killer_player_slot) === selectedSlot) {
      const victimLabel = victim.hero_name || `slot ${victim.player_slot}`;
      return [{
        type: "kill",
        time: eventTime,
        chips: [
          `<span class="deltaChip">killed ${victimLabel}</span>`,
          timeToKill ? `<span class="deltaChip">${timeToKill}</span>` : "",
          victimDeathDuration ? `<span class="deltaChip">${victimDeathDuration}</span>` : "",
        ].filter(Boolean).join(""),
      }];
    }
    return [];
  }).sort((a, b) => a.time - b.time);

  if (!events.length) {
    el.killDeathTimeline.innerHTML = `<p class="subtle">No exact kills or deaths for this player in the stored death details.</p>`;
    return;
  }

  el.killDeathTimeline.innerHTML = events.map((event) => `
    <div class="combatEvent ${event.type === "kill" ? "killEvent" : "deathEvent"}">
      <span class="combatTime">${mmss(event.time)}</span>
      <span class="combatDeltas">${event.chips}</span>
    </div>
  `).join("");
}

function renderFinalStats(player) {
  const stats = player.finalStats || {};
  el.finalStatsNote.textContent = "Final cumulative values grouped by role";
  const groups = [
    {
      title: "Damage",
      fields: [
        ["Player damage", stats.player_damage],
        ["Boss damage", stats.boss_damage],
        ["Creep damage", stats.creep_damage],
        ["Neutral damage", stats.neutral_damage],
      ],
    },
    {
      title: "Defense",
      fields: [
        ["Damage taken", stats.player_damage_taken],
        ["Mitigated", stats.damage_mitigated],
        ["Absorbed", stats.damage_absorbed],
        ["Max health", stats.max_health],
      ],
    },
    {
      title: "Healing / Barrier",
      fields: [
        ["Player healing", stats.player_healing],
        ["Self healing", stats.self_healing],
        ["Teammate healing", stats.teammate_healing],
        ["Player barrier", stats.player_barriering],
        ["Team barrier", stats.teammate_barriering],
        ["Absorption provided", stats.absorption_provided],
      ],
    },
    {
      title: "Economy",
      fields: [
        ["Net worth", stats.net_worth],
        ["Player souls", stats.gold_player],
        ["Lane souls", stats.gold_lane_creep],
        ["Neutral souls", stats.gold_neutral_creep],
        ["Boss souls", stats.gold_boss],
        ["Death loss", stats.gold_death_loss],
      ],
    },
    {
      title: "Farm",
      fields: [
        ["Creep kills", stats.creep_kills],
        ["Neutral kills", stats.neutral_kills],
        ["Denies", stats.denies],
        ["Possible creeps", stats.possible_creeps],
      ],
    },
    {
      title: "Combat Style",
      fields: [
        ["Ability kills", stats.ability_kills],
        ["Bullet kills", stats.bullet_kills],
        ["Melee kills", stats.melee_kills],
        ["Headshot kills", stats.headshot_kills],
        ["Shots hit", stats.shots_hit],
        ["Shots missed", stats.shots_missed],
      ],
    },
    {
      title: "Scaling",
      fields: [
        ["Level", stats.level],
        ["Ability points", stats.ability_points],
        ["Weapon power", stats.weapon_power],
        ["Tech power", stats.tech_power],
      ],
    },
  ];

  el.finalStats.innerHTML = groups.map((group) => `
    <section class="finalStatGroup">
      <h4>${group.title}</h4>
      <div class="finalStatGrid">
        ${group.fields.map(([label, value]) => `
          <div class="statBox">
            <span>${label}</span>
            <strong>${fmt(value)}</strong>
          </div>
        `).join("")}
      </div>
    </section>
  `).join("");
}

function debounce(fn, delay = 250) {
  let timeout = null;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}

document.querySelectorAll(".chartTab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".chartTab").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.metric = button.dataset.metric;
    const player = selectedPlayer();
    if (player) renderChart(player);
  });
});

el.percentileInput.addEventListener("input", () => {
  el.percentileValue.textContent = el.percentileInput.value;
  saveFilters();
});
el.percentileInput.addEventListener("change", saveFiltersAndLoadPerformances);
el.minDurationInput.addEventListener("input", debounce(saveFiltersAndLoadPerformances));
el.maxDurationInput.addEventListener("input", debounce(saveFiltersAndLoadPerformances));
el.minKdaInput.addEventListener("input", debounce(saveFiltersAndLoadPerformances));
el.searchInput.addEventListener("input", debounce(saveFiltersAndLoadPerformances));
el.refreshButton.addEventListener("click", loadPerformances);

loadSavedFilters();

loadSummary()
  .then(loadPerformances)
  .catch((error) => {
    el.datasetSummary.textContent = error.message;
    el.performanceList.innerHTML = `<p class="subtle">${error.message}</p>`;
  });
