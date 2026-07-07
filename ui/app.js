const state = {
  performances: [],
  selectedPerformance: null,
  selectedMatch: null,
  selectedPlayerSlot: null,
  metric: "player_damage",
  timelineEventTypes: new Set(["item", "ability", "kill", "death", "assist", "neutral"]),
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
  timelineToggles: document.querySelectorAll(".timelineToggle"),
  fullTimeline: document.querySelector("#fullTimeline"),
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
const TIMELINE_EVENT_TYPES = ["item", "ability", "kill", "death", "assist", "neutral"];
const SEPARATE_SELL_EVENT_SECONDS = 60;

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
    timelineEventTypes: Array.from(state.timelineEventTypes),
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
  if (Array.isArray(filters.timelineEventTypes)) {
    state.timelineEventTypes = new Set(
      filters.timelineEventTypes.filter((type) => TIMELINE_EVENT_TYPES.includes(type))
    );
  }
  el.percentileValue.textContent = el.percentileInput.value;
  updateTimelineToggleButtons();
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
  const { abilityItems, shopItems } = timelineParts(player);

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
  renderFullTimeline(player, shopItems, abilityItems);
  renderFinalStats(player);
}

function renderNetWorthEstimate(label, estimate) {
  if (!estimate || estimate.value === null || estimate.value === undefined) return "";
  const sampleTime = estimate.timeText ? ` @ ${estimate.timeText}` : "";
  return `<span>${label} ~${fmt(estimate.value)} NW${sampleTime}</span>`;
}

function itemCostLabel(item) {
  const cost = Number(item.asset?.cost ?? item.cost);
  if (!Number.isFinite(cost) || cost <= 0) return "";
  return `${fmt(cost)} souls`;
}

function abilityRankLabel(item) {
  const rank = Number(item.abilityRank);
  if (!Number.isFinite(rank) || rank <= 0) return "";
  return `rank ${rank}`;
}

function imbueLabel(item) {
  if (item.imbuedAbility?.name) return `imbued: ${item.imbuedAbility.name}`;
  const imbuedAbilityId = Number(item.imbued_ability_id);
  if (!Number.isFinite(imbuedAbilityId) || imbuedAbilityId <= 0) return "";
  return `imbued: ability ${imbuedAbilityId}`;
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
  const imbue = imbueLabel(item);
  const itemMeta = [
    item.asset?.slot || item.asset?.type || "shop",
    itemCostLabel(item),
    item.sold_time_s ? `sold ${mmss(item.sold_time_s)}` : "",
  ].filter(Boolean).join(" · ");
  return `
    <div class="itemBuy ${shopItemTypeClass(item)}">
      <span class="meta">${item.timeText || mmss(item.game_time_s)}</span>
      <img src="${item.asset?.image || ""}" alt="">
      <span class="itemInfo">
        <strong>${item.item_name || item.asset?.name || item.item_id || "Unknown item"}</strong>
        <span class="meta">${itemMeta}</span>
        ${imbue ? `<span class="imbueBadge">${imbue}</span>` : ""}
      </span>
      <span class="meta nwEstimate">${netWorthLines || "-"}</span>
    </div>
  `;
}

function renderAbilityItem(item) {
  const step = item.abilityStep || (Number(item.upgrade_id || 0) === 0 ? "unlock" : "upgrade");
  const rankLabel = abilityRankLabel(item);
  return `
    <div class="itemBuy abilityBuy">
      <span class="meta">${item.timeText || mmss(item.game_time_s)}</span>
      <img src="${item.asset?.image || ""}" alt="">
      <span>
        <strong>${item.item_name || item.asset?.name || item.item_id || "Unknown ability"}</strong>
        <span class="meta">${[step, rankLabel].filter(Boolean).join(" · ")}</span>
      </span>
      <span class="abilityStep ${step}">${rankLabel || step}</span>
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

function playerBySlot(slot) {
  if (!state.selectedMatch) return null;
  return state.selectedMatch.players.find((player) => Number(player.player_slot) === Number(slot)) || null;
}

function fullTimelineChip(label) {
  return `<span class="deltaChip">${label}</span>`;
}

function itemTimelineEvents(items) {
  return items.flatMap((item) => {
    const buyTime = Number(item.game_time_s || 0);
    const sellTime = Number(item.sold_time_s || 0);
    const hasSeparateSellEvent = sellTime > 0 && sellTime - buyTime > SEPARATE_SELL_EVENT_SECONDS;
    const title = item.item_name || item.asset?.name || item.item_id || "Unknown item";
    const costLabel = itemCostLabel(item);
    const imbue = imbueLabel(item);
    const events = [{
      type: "item",
      typeClass: shopItemTypeClass(item),
      time: buyTime,
      timeLabel: item.timeText || mmss(item.game_time_s),
      image: item.asset?.image || "",
      title,
      chips: [
        fullTimelineChip(item.asset?.slot || item.asset?.type || "shop item"),
        costLabel ? fullTimelineChip(costLabel) : "",
        imbue ? fullTimelineChip(imbue) : "",
        item.sold_time_s && !hasSeparateSellEvent ? fullTimelineChip(`sold ${mmss(item.sold_time_s)}`) : "",
      ].filter(Boolean).join(""),
    }];
    if (hasSeparateSellEvent) {
      events.push({
        type: "item",
        typeClass: `sellEvent ${shopItemTypeClass(item)}`,
        time: sellTime,
        timeLabel: mmss(sellTime),
        image: item.asset?.image || "",
        title: `Sold ${title}`,
        chips: [
          fullTimelineChip(item.asset?.slot || item.asset?.type || "shop item"),
        ].filter(Boolean).join(""),
      });
    }
    return events;
  });
}

function abilityTimelineEvents(items) {
  return items.map((item) => {
    const step = item.abilityStep || (Number(item.upgrade_id || 0) === 0 ? "unlock" : "upgrade");
    const rankLabel = abilityRankLabel(item);
    return {
      type: "ability",
      time: Number(item.game_time_s || 0),
      timeLabel: item.timeText || mmss(item.game_time_s),
      image: item.asset?.image || "",
      title: item.item_name || item.asset?.name || item.item_id || "Unknown ability",
      chips: [
        fullTimelineChip(step),
        rankLabel ? fullTimelineChip(rankLabel) : "",
      ].filter(Boolean).join(""),
    };
  });
}

function killDeathTimelineEvents(player) {
  const selectedSlot = Number(player.player_slot);
  const allDeathDetails = (state.selectedMatch?.players || []).flatMap((victim) => (
    (victim.deathDetails || []).map((detail) => ({ detail, victim }))
  ));

  return allDeathDetails.flatMap(({ detail, victim }) => {
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
        timeLabel: mmss(eventTime),
        title: "Death",
        chips: [
          fullTimelineChip(`died to ${killerLabel}`),
          timeToKill ? fullTimelineChip(timeToKill) : "",
          deathDuration ? fullTimelineChip(deathDuration) : "",
        ].filter(Boolean).join(""),
      }];
    }
    if (Number(detail.killer_player_slot) === selectedSlot) {
      const victimLabel = victim.hero_name || `slot ${victim.player_slot}`;
      return [{
        type: "kill",
        time: eventTime,
        timeLabel: mmss(eventTime),
        title: "Kill",
        chips: [
          fullTimelineChip(`killed ${victimLabel}`),
          timeToKill ? fullTimelineChip(timeToKill) : "",
          victimDeathDuration ? fullTimelineChip(victimDeathDuration) : "",
        ].filter(Boolean).join(""),
      }];
    }
    return [];
  });
}

function windowTimelineEvents(player) {
  const samples = player.stats || [];
  const events = [];
  for (let index = 1; index < samples.length; index += 1) {
    const previous = samples[index - 1];
    const current = samples[index];
    const assists = statDelta(current, previous, "assists");
    const neutralKills = statDelta(current, previous, "neutral_kills");
    const hasAssists = assists && state.timelineEventTypes.has("assist");
    const hasNeutrals = neutralKills && state.timelineEventTypes.has("neutral");
    if (!hasAssists && !hasNeutrals) continue;

    const titleParts = [
      hasAssists ? `${fmt(assists)} assist${assists === 1 ? "" : "s"}` : "",
      hasNeutrals ? `${fmt(neutralKills)} neutral${neutralKills === 1 ? "" : "s"}` : "",
    ].filter(Boolean);
    const chips = [
      fullTimelineChip("sample window"),
      hasAssists ? fullTimelineChip("assist timing approximate") : "",
      hasNeutrals ? fullTimelineChip("neutral timing approximate") : "",
    ].filter(Boolean);

    events.push({
      type: "window",
      lane: "window",
      startTime: Number(previous.time_stamp_s || 0),
      endTime: Number(current.time_stamp_s || 0),
      time: Number(current.time_stamp_s || 0),
      timeLabel: `${previous.timeText || mmss(previous.time_stamp_s)}-${current.timeText || mmss(current.time_stamp_s)}`,
      title: titleParts.join(" · "),
      chips: chips.join(""),
    });
  }
  return events;
}

function timelineEventCard(event) {
  return `
    <div class="timelineEvent ${event.type}Event ${event.lane === "window" ? "windowEvent" : ""} ${event.typeClass || ""}">
      <span class="combatTime">${event.timeLabel || mmss(event.time)}</span>
      ${event.image ? `<img src="${event.image}" alt="">` : `<span class="timelineIcon">${event.type}</span>`}
      <span>
        <strong>${event.title}</strong>
        <span class="combatDeltas">${event.chips}</span>
      </span>
    </div>
  `;
}

function timelineRows(events) {
  const mainEvents = events.filter((event) => event.lane !== "window");
  const windowEvents = events.filter((event) => event.lane === "window");
  const rows = windowEvents.map((event) => ({
    startTime: event.startTime ?? event.time,
    endTime: event.endTime ?? event.time,
    main: [],
    windows: [event],
  }));
  for (const event of mainEvents) {
    const matchingRow = rows.find((row) => event.time >= row.startTime && event.time <= row.endTime);
    if (matchingRow) {
      matchingRow.main.push(event);
    } else {
      rows.push({ startTime: event.time, endTime: event.time, main: [event], windows: [] });
    }
  }
  return rows
    .map((row) => ({
      ...row,
      main: row.main.sort((a, b) => a.time - b.time || String(a.type).localeCompare(String(b.type))),
      windows: row.windows.sort((a, b) => a.time - b.time),
    }))
    .sort((a, b) => a.startTime - b.startTime);
}

function groupedMainTimelineCards(events) {
  const groups = [];
  for (const event of events) {
    const group = groups.find((existing) => existing.time === event.time);
    if (group) {
      group.events.push(event);
    } else {
      groups.push({ time: event.time, events: [event] });
    }
  }

  return groups.map((group) => `
    <div class="timelineMainGroup${group.events.length > 1 ? " sameTimeGroup" : ""}" style="--timeline-columns: ${group.events.length}">
      ${group.events.map(timelineEventCard).join("")}
    </div>
  `).join("");
}

function renderFullTimeline(player, shopItems, abilityItems) {
  const allEvents = [
    ...itemTimelineEvents(shopItems),
    ...abilityTimelineEvents(abilityItems),
    ...killDeathTimelineEvents(player),
    ...windowTimelineEvents(player),
  ].sort((a, b) => a.time - b.time || String(a.type).localeCompare(String(b.type)));
  const events = allEvents.filter((event) => event.lane === "window" || state.timelineEventTypes.has(event.type));

  if (!allEvents.length) {
    el.fullTimeline.innerHTML = `<p class="subtle">No build or combat timeline events stored for this player.</p>`;
    return;
  }
  if (!events.length) {
    el.fullTimeline.innerHTML = `<p class="subtle">No timeline events match the selected type filters.</p>`;
    return;
  }

  el.fullTimeline.innerHTML = timelineRows(events).map((row) => `
    <div class="timelineRow">
      <div class="timelineLane mainLane">${groupedMainTimelineCards(row.main)}</div>
      <div class="timelineLane windowLane">${row.windows.map(timelineEventCard).join("")}</div>
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

function timelineParts(player) {
  const abilityItems = (player.items || []).filter((item) => item.itemKind === "ability" || item.asset?.type === "ability");
  const shopItems = (player.items || []).filter((item) => !(item.itemKind === "ability" || item.asset?.type === "ability"));
  return { abilityItems, shopItems };
}

function renderSelectedFullTimeline() {
  const player = selectedPlayer();
  if (!player) return;
  const { abilityItems, shopItems } = timelineParts(player);
  renderFullTimeline(player, shopItems, abilityItems);
}

function updateTimelineToggleButtons() {
  el.timelineToggles.forEach((button) => {
    const enabled = state.timelineEventTypes.has(button.dataset.eventType);
    button.classList.toggle("active", enabled);
    button.setAttribute("aria-pressed", enabled ? "true" : "false");
  });
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

el.timelineToggles.forEach((button) => {
  button.addEventListener("click", () => {
    const eventType = button.dataset.eventType;
    if (!TIMELINE_EVENT_TYPES.includes(eventType)) return;
    if (state.timelineEventTypes.has(eventType)) {
      state.timelineEventTypes.delete(eventType);
    } else {
      state.timelineEventTypes.add(eventType);
    }
    updateTimelineToggleButtons();
    saveFilters();
    renderSelectedFullTimeline();
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
