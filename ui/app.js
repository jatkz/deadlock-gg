const state = {
  performances: [],
  heroes: [],
  heroComparison: null,
  selectedHeroComparisonIds: new Set(),
  selectedHeroComparisonColumns: new Set(),
  heroComparisonSort: { key: "dps", direction: "desc" },
  itemResultsById: new Map(),
  matchItemResultsById: new Map(),
  selectedPerformance: null,
  selectedMatch: null,
  selectedPlayerSlot: null,
  selectedHeroData: null,
  abilitySheet: null,
  abilitySheetCollapsed: false,
  matchItemLabCollapsed: false,
  matchItemLab: null,
  abilitySheetSort: { key: "team", direction: "asc" },
  metric: "player_damage",
  scoreboardSort: "lane",
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
  enemyLaneHeroInput: document.querySelector("#enemyLaneHeroInput"),
  savedOnlyInput: document.querySelector("#savedOnlyInput"),
  heroDataButton: document.querySelector("#heroDataButton"),
  heroCompareButton: document.querySelector("#heroCompareButton"),
  itemLabButton: document.querySelector("#itemLabButton"),
  refreshButton: document.querySelector("#refreshButton"),
  performanceList: document.querySelector("#performanceList"),
  resultCount: document.querySelector("#resultCount"),
  emptyState: document.querySelector("#emptyState"),
  heroData: document.querySelector("#heroData"),
  heroDataSummary: document.querySelector("#heroDataSummary"),
  heroDataInput: document.querySelector("#heroDataInput"),
  heroDataOptions: document.querySelector("#heroDataOptions"),
  loadHeroDataButton: document.querySelector("#loadHeroDataButton"),
  heroRawToggle: document.querySelector("#heroRawToggle"),
  heroDataContent: document.querySelector("#heroDataContent"),
  heroCompare: document.querySelector("#heroCompare"),
  heroCompareSummary: document.querySelector("#heroCompareSummary"),
  heroCompareSearchInput: document.querySelector("#heroCompareSearchInput"),
  heroCompareSortInput: document.querySelector("#heroCompareSortInput"),
  heroCompareSortDirectionButton: document.querySelector("#heroCompareSortDirectionButton"),
  clearHeroCompareButton: document.querySelector("#clearHeroCompareButton"),
  heroComparePicker: document.querySelector("#heroComparePicker"),
  heroCompareColumnPicker: document.querySelector("#heroCompareColumnPicker"),
  heroCompareCount: document.querySelector("#heroCompareCount"),
  heroCompareContent: document.querySelector("#heroCompareContent"),
  itemLab: document.querySelector("#itemLab"),
  itemLabSummary: document.querySelector("#itemLabSummary"),
  itemHeroInput: document.querySelector("#itemHeroInput"),
  itemEnemiesInput: document.querySelector("#itemEnemiesInput"),
  ownedItemsInput: document.querySelector("#ownedItemsInput"),
  itemSearchInput: document.querySelector("#itemSearchInput"),
  gameMinuteInput: document.querySelector("#gameMinuteInput"),
  itemMinMatchesInput: document.querySelector("#itemMinMatchesInput"),
  enemyScopeInput: document.querySelector("#enemyScopeInput"),
  includeAbilitiesInput: document.querySelector("#includeAbilitiesInput"),
  discoverItemsButton: document.querySelector("#discoverItemsButton"),
  recommendItemsButton: document.querySelector("#recommendItemsButton"),
  itemResultsTitle: document.querySelector("#itemResultsTitle"),
  itemResultCount: document.querySelector("#itemResultCount"),
  itemResults: document.querySelector("#itemResults"),
  itemEvidence: document.querySelector("#itemEvidence"),
  matchDetail: document.querySelector("#matchDetail"),
  featuredHeroCard: document.querySelector("#featuredHeroCard"),
  matchMeta: document.querySelector("#matchMeta"),
  featuredTitle: document.querySelector("#featuredTitle"),
  featuredStats: document.querySelector("#featuredStats"),
  saveMatchButton: document.querySelector("#saveMatchButton"),
  saveMatchStatus: document.querySelector("#saveMatchStatus"),
  scoreboard: document.querySelector("#scoreboard"),
  scoreboardSortInput: document.querySelector("#scoreboardSortInput"),
  scoreNote: document.querySelector("#scoreNote"),
  abilitySheetSummary: document.querySelector("#abilitySheetSummary"),
  abilitySheetMinuteInput: document.querySelector("#abilitySheetMinuteInput"),
  abilitySheetScalingInput: document.querySelector("#abilitySheetScalingInput"),
  loadAbilitySheetButton: document.querySelector("#loadAbilitySheetButton"),
  toggleAbilitySheetButton: document.querySelector("#toggleAbilitySheetButton"),
  abilitySheetBody: document.querySelector("#abilitySheetBody"),
  abilitySheet: document.querySelector("#abilitySheet"),
  matchItemLabSummary: document.querySelector("#matchItemLabSummary"),
  matchItemPlayerInput: document.querySelector("#matchItemPlayerInput"),
  matchItemMinuteInput: document.querySelector("#matchItemMinuteInput"),
  matchItemMinMatchesInput: document.querySelector("#matchItemMinMatchesInput"),
  matchItemIncludeAbilitiesInput: document.querySelector("#matchItemIncludeAbilitiesInput"),
  toggleMatchItemLabButton: document.querySelector("#toggleMatchItemLabButton"),
  matchItemLabBody: document.querySelector("#matchItemLabBody"),
  loadMatchItemLabButton: document.querySelector("#loadMatchItemLabButton"),
  matchItemContext: document.querySelector("#matchItemContext"),
  matchItemResults: document.querySelector("#matchItemResults"),
  matchItemEvidence: document.querySelector("#matchItemEvidence"),
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
const HERO_COMPARE_STORAGE_KEY = "deadlockHeroCompareSettings";
const TIMELINE_EVENT_TYPES = ["item", "ability", "kill", "death", "assist", "neutral"];
const SEPARATE_SELL_EVENT_SECONDS = 60;
const GROUP_NEARBY_ITEM_EVENT_SECONDS = 1;
const SUMMARY_WINDOW_SECONDS = 180;
const HERO_COMPARE_LIMIT = 6;
const HERO_COMPARE_COLUMNS = [
  "dps",
  "sustained_dps",
  "bullet_damage",
  "bullets_per_sec",
  "ammo",
  "reload_time_s",
  "max_health",
  "health_regen",
  "bullet_resist",
  "spirit_resist",
  "move_speed_m_s",
  "sprint_speed_m",
  "stamina",
  "dash_speed_m",
  "spirit_power",
];

function defaultHeroCompareColumns(columns = []) {
  const available = new Set(columns);
  return HERO_COMPARE_COLUMNS.filter((column) => available.has(column));
}

function fmt(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toLocaleString();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  }[char]));
}

function pct(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

function rankText(averageBadge) {
  if (!averageBadge || typeof averageBadge !== "object") return "";
  return averageBadge.label || "";
}

function rankMeta(averageBadge) {
  const label = rankText(averageBadge);
  return label ? `Rank ${label}` : "Rank unavailable";
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

function secondsFromMinuteValue(input) {
  const raw = input.value.trim();
  if (!raw) return "";
  const minutes = Number(raw);
  if (!Number.isFinite(minutes) || minutes < 0) return "";
  return String(Math.round(minutes * 60));
}

function currentFilters() {
  return {
    minPercentile: el.percentileInput.value,
    minDuration: el.minDurationInput.value,
    maxDuration: el.maxDurationInput.value,
    minKda: el.minKdaInput.value,
    search: el.searchInput.value,
    enemyLaneHero: el.enemyLaneHeroInput.value,
    savedOnly: el.savedOnlyInput.checked,
    scoreboardSort: state.scoreboardSort,
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
  if (filters.enemyLaneHero !== undefined) el.enemyLaneHeroInput.value = String(filters.enemyLaneHero);
  if (filters.savedOnly !== undefined) el.savedOnlyInput.checked = Boolean(filters.savedOnly);
  if (["lane", "score", "slot"].includes(filters.scoreboardSort)) {
    state.scoreboardSort = filters.scoreboardSort;
    el.scoreboardSortInput.value = filters.scoreboardSort;
  }
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

function loadHeroCompareSettings() {
  try {
    const settings = JSON.parse(localStorage.getItem(HERO_COMPARE_STORAGE_KEY));
    if (!settings || typeof settings !== "object") return;
    if (Array.isArray(settings.heroIds)) {
      state.selectedHeroComparisonIds = new Set(settings.heroIds.map(String));
    }
    if (Array.isArray(settings.columns)) {
      state.selectedHeroComparisonColumns = new Set(settings.columns.map(String));
    }
    if (settings.sort && typeof settings.sort === "object") {
      const key = String(settings.sort.key || "");
      const direction = settings.sort.direction === "asc" ? "asc" : "desc";
      if (key) state.heroComparisonSort = { key, direction };
    }
  } catch (_error) {
    try {
      localStorage.removeItem(HERO_COMPARE_STORAGE_KEY);
    } catch (_ignored) {
      // Ignore storage failures; compare settings still work for the current page.
    }
  }
}

function saveHeroCompareSettings() {
  try {
    localStorage.setItem(HERO_COMPARE_STORAGE_KEY, JSON.stringify({
      heroIds: Array.from(state.selectedHeroComparisonIds),
      columns: Array.from(state.selectedHeroComparisonColumns),
      sort: state.heroComparisonSort,
    }));
  } catch (_error) {
    // Ignore storage failures; compare settings still work for the current page.
  }
}

async function getJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

async function postJson(url) {
  const response = await fetch(url, { method: "POST" });
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
  const enemyLaneHero = el.enemyLaneHeroInput.value.trim();
  if (minDurationS) params.set("minDurationS", minDurationS);
  if (maxDurationS) params.set("maxDurationS", maxDurationS);
  if (minKda) params.set("minKda", minKda);
  if (enemyLaneHero) params.set("enemyLaneHero", enemyLaneHero);
  if (el.savedOnlyInput.checked) params.set("savedOnly", "1");
  const payload = await getJson(`/api/performances?${params.toString()}`);
  state.performances = payload.items;
  el.resultCount.textContent = `${fmt(payload.totalMatched)} found`;
  renderPerformanceList();
  if (!state.performances.length) {
    clearSelectedPerformance("No performances match the current filters.");
    return;
  }
  await selectPerformance(state.performances[0]);
}

function renderPerformanceList() {
  el.performanceList.innerHTML = "";
  if (!state.performances.length) {
    el.performanceList.innerHTML = `<p class="subtle">No performances match the current filters.</p>`;
    return;
  }
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
    const laneMatchup = enemyLaneText(perf);
    const matchRank = rankText(perf.averageBadge);
    button.innerHTML = `
      <img class="heroIcon" src="${perf.hero?.icon || ""}" alt="">
      <span class="perfMain">
        <strong>${perf.heroName || "Unknown hero"}</strong>
        <span class="meta">Match ${perf.matchId} · ${perf.durationText} · <span class="${perf.won ? "win" : "loss"}">${perf.won ? "Win" : "Loss"}</span>${matchRank ? ` · ${matchRank}` : ""}</span>
        ${laneMatchup ? `<span class="meta">${laneMatchup}</span>` : ""}
        <span class="meta">${fmt(perf.kills)}/${fmt(perf.deaths)}/${fmt(perf.assists)} · ${fmt(perf.kdaRatio)} KDA · ${fmt(perf.netWorth)} NW · ${fmt(perf.playerDamage)} dmg</span>
        <span class="reasonTags">${(perf.reasons || []).map((reason) => `<span class="reasonTag">${reason}</span>`).join("")}</span>
      </span>
      <span class="perfScore">
        <strong>${pct(perf.percentile)}</strong>
        ${matchRank ? `<span class="rankLabel">${matchRank}</span>` : ""}
        <span class="meta">${fmt(perf.score)}</span>
      </span>
    `;
    button.addEventListener("click", () => selectPerformance(perf));
    el.performanceList.appendChild(button);
  }
}

function clearSelectedPerformance(message) {
  state.selectedPerformance = null;
  state.selectedMatch = null;
  state.selectedPlayerSlot = null;
  el.matchDetail.classList.add("hidden");
  el.heroData.classList.add("hidden");
  el.heroCompare.classList.add("hidden");
  el.itemLab.classList.add("hidden");
  el.emptyState.classList.remove("hidden");
  el.emptyState.textContent = message || "Select a performance to inspect the match, build route, combat timeline, and final stats.";
}

async function selectPerformance(perf) {
  state.selectedPerformance = perf;
  state.selectedPlayerSlot = perf.playerSlot;
  state.selectedMatch = await getJson(`/api/matches/${perf.matchId}`);
  el.heroData.classList.add("hidden");
  el.heroCompare.classList.add("hidden");
  el.itemLab.classList.add("hidden");
  renderPerformanceList();
  renderMatch();
}

function showHeroData(loadInitial = true) {
  el.emptyState.classList.add("hidden");
  el.matchDetail.classList.add("hidden");
  el.heroCompare.classList.add("hidden");
  el.itemLab.classList.add("hidden");
  el.heroData.classList.remove("hidden");
  if (!el.heroDataInput.value.trim() && state.selectedPerformance?.heroName) {
    el.heroDataInput.value = state.selectedPerformance.heroName;
  }
  if (loadInitial) loadHeroData();
}

function showHeroCompare(loadInitial = true) {
  el.emptyState.classList.add("hidden");
  el.matchDetail.classList.add("hidden");
  el.heroData.classList.add("hidden");
  el.itemLab.classList.add("hidden");
  el.heroCompare.classList.remove("hidden");
  if (loadInitial) loadHeroComparison();
}

function showItemLab(loadInitial = true) {
  el.emptyState.classList.add("hidden");
  el.matchDetail.classList.add("hidden");
  el.heroData.classList.add("hidden");
  el.heroCompare.classList.add("hidden");
  el.itemLab.classList.remove("hidden");
  if (loadInitial && !el.itemResults.dataset.loaded) loadItemMatchups("recommend");
}

async function loadHeroList() {
  const payload = await getJson("/api/heroes");
  state.heroes = payload.items || [];
  el.heroDataOptions.innerHTML = state.heroes.map((hero) => `
    <option value="${escapeHtml(hero.name)}">${escapeHtml(hero.className || hero.id)}</option>
  `).join("");
}

function columnLabel(column) {
  return String(column || "")
    .split("_")
    .filter(Boolean)
    .map((part) => part.length <= 3 ? part.toUpperCase() : part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function heroCompareId(row) {
  return String(row?.row_index || row?.hero?.id || row?.values?.hero || "");
}

function heroCompareName(row) {
  return row?.values?.hero || row?.raw?.hero || row?.hero?.name || "Unknown";
}

function heroCompareRows() {
  return state.heroComparison?.items || [];
}

function selectedHeroCompareRows() {
  const rows = heroCompareRows().filter((row) => state.selectedHeroComparisonIds.has(heroCompareId(row)));
  return rows.sort((a, b) => compareHeroRows(a, b, state.heroComparisonSort.key, state.heroComparisonSort.direction));
}

function ensureHeroCompareSelection(rows) {
  if (state.selectedHeroComparisonIds.size || !rows.length) return;
  const names = [state.selectedPerformance?.heroName, "Abrams", "Haze", "Seven", "Wraith"].filter(Boolean);
  for (const name of names) {
    const row = rows.find((item) => searchTokenMatches(heroCompareName(item), name));
    if (row) state.selectedHeroComparisonIds.add(heroCompareId(row));
    if (state.selectedHeroComparisonIds.size >= 4) break;
  }
  if (!state.selectedHeroComparisonIds.size) {
    for (const row of rows.slice(0, 4)) state.selectedHeroComparisonIds.add(heroCompareId(row));
  }
  saveHeroCompareSettings();
}

function ensureHeroCompareColumns(columns = []) {
  const available = new Set(columns);
  state.selectedHeroComparisonColumns = new Set(
    Array.from(state.selectedHeroComparisonColumns).filter((column) => available.has(column))
  );
  if (!state.selectedHeroComparisonColumns.size) {
    state.selectedHeroComparisonColumns = new Set(defaultHeroCompareColumns(columns));
    saveHeroCompareSettings();
  }
  if (!available.has(state.heroComparisonSort.key)) {
    state.heroComparisonSort.key = state.selectedHeroComparisonColumns.values().next().value || columns[0] || "hero";
    saveHeroCompareSettings();
  }
}

function sortableValue(row, column) {
  const value = row?.values?.[column];
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : String(value).toLowerCase();
}

function compareHeroRows(a, b, column, direction) {
  const left = sortableValue(a, column);
  const right = sortableValue(b, column);
  const multiplier = direction === "asc" ? 1 : -1;
  if (left === null && right === null) return heroCompareName(a).localeCompare(heroCompareName(b));
  if (left === null) return 1;
  if (right === null) return -1;
  if (typeof left === "number" && typeof right === "number" && left !== right) {
    return (left - right) * multiplier;
  }
  const compared = String(left).localeCompare(String(right), undefined, { numeric: true });
  return compared ? compared * multiplier : heroCompareName(a).localeCompare(heroCompareName(b));
}

function searchTokenMatches(value, query) {
  const cleanValue = String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  const cleanQuery = String(query || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  return cleanQuery ? cleanValue.includes(cleanQuery) : true;
}

function renderHeroComparePicker() {
  const rows = heroCompareRows();
  const query = el.heroCompareSearchInput.value.trim();
  const filtered = rows
    .filter((row) => searchTokenMatches(heroCompareName(row), query))
    .slice(0, 24);
  if (!filtered.length) {
    el.heroComparePicker.innerHTML = `<p class="subtle">No heroes match that search.</p>`;
    return;
  }
  el.heroComparePicker.innerHTML = filtered.map((row) => {
    const id = heroCompareId(row);
    const checked = state.selectedHeroComparisonIds.has(id) ? " checked" : "";
    return `
      <label class="heroCompareOption">
        <input type="checkbox" value="${escapeHtml(id)}"${checked}>
        <img src="${escapeHtml(row.hero?.icon || "")}" alt="">
        <span>
          <strong>${escapeHtml(heroCompareName(row))}</strong>
          <small>${escapeHtml(fmt(row.values?.dps))} DPS · ${escapeHtml(fmt(row.values?.max_health))} HP</small>
        </span>
      </label>
    `;
  }).join("");
}

function renderHeroCompareControls() {
  const columns = state.heroComparison?.columns || [];
  ensureHeroCompareColumns(columns);
  const selectedColumns = Array.from(state.selectedHeroComparisonColumns);
  el.heroCompareSortInput.innerHTML = selectedColumns.map((column) => `
    <option value="${escapeHtml(column)}"${column === state.heroComparisonSort.key ? " selected" : ""}>${escapeHtml(columnLabel(column))}</option>
  `).join("");
  el.heroCompareSortDirectionButton.textContent = state.heroComparisonSort.direction === "asc" ? "Asc" : "Desc";
  el.heroCompareSortDirectionButton.title = state.heroComparisonSort.direction === "asc" ? "Sort low to high" : "Sort high to low";
  el.heroCompareColumnPicker.innerHTML = columns
    .filter((column) => column !== "hero")
    .map((column) => {
      const checked = state.selectedHeroComparisonColumns.has(column) ? " checked" : "";
      return `
        <label class="heroCompareColumnOption">
          <input type="checkbox" value="${escapeHtml(column)}"${checked}>
          <span>${escapeHtml(columnLabel(column))}</span>
        </label>
      `;
    }).join("");
}

function renderHeroCompareContent() {
  const rows = selectedHeroCompareRows();
  const availableColumns = Array.from(state.selectedHeroComparisonColumns)
    .filter((column) => state.heroComparison?.columns?.includes(column));
  el.heroCompareCount.textContent = `${fmt(rows.length)} heroes · ${fmt(availableColumns.length)} stats`;
  if (!rows.length) {
    el.heroCompareContent.innerHTML = `<p class="subtle">Select heroes to compare their wiki table stats.</p>`;
    return;
  }
  if (!availableColumns.length) {
    el.heroCompareContent.innerHTML = `<p class="subtle">Select at least one stat to show.</p>`;
    return;
  }
  el.heroCompareContent.innerHTML = `
    <div class="heroCompareStrip">
      ${rows.map((row) => `
        <article class="heroCompareHero">
          <img src="${escapeHtml(row.hero?.icon || "")}" alt="">
          <div>
            <strong>${escapeHtml(heroCompareName(row))}</strong>
            <span class="meta">${escapeHtml(fmt(row.values?.dps))} DPS · ${escapeHtml(fmt(row.values?.max_health))} HP · ${escapeHtml(fmt(row.values?.move_speed_m_s))} m/s</span>
          </div>
        </article>
      `).join("")}
    </div>
    <div class="heroCompareTableWrap">
      <table class="heroCompareTable">
        <thead>
          <tr>
            <th>Stat</th>
            ${rows.map((row) => `<th>${escapeHtml(heroCompareName(row))}</th>`).join("")}
          </tr>
        </thead>
        <tbody>
          ${availableColumns.map((column) => `
            <tr>
              <th>
                <button class="heroCompareStatSort" type="button" data-column="${escapeHtml(column)}">
                  ${escapeHtml(columnLabel(column))}
                  ${state.heroComparisonSort.key === column ? `<span>${state.heroComparisonSort.direction === "asc" ? "Asc" : "Desc"}</span>` : ""}
                </button>
              </th>
              ${rows.map((row) => `
                <td>
                  <strong>${escapeHtml(fmt(row.values?.[column]))}</strong>
                  ${row.raw?.[column] && String(row.raw[column]) !== String(row.values?.[column] ?? "") ? `<span>${escapeHtml(row.raw[column])}</span>` : ""}
                </td>
              `).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderHeroComparison() {
  const payload = state.heroComparison;
  const rows = heroCompareRows();
  ensureHeroCompareSelection(rows);
  el.heroCompareSummary.textContent = `${fmt(payload?.counts?.heroes || rows.length)} rows · ${fmt(payload?.counts?.columns || payload?.columns?.length || 0)} columns`;
  renderHeroCompareControls();
  renderHeroComparePicker();
  renderHeroCompareContent();
}

async function loadHeroComparison() {
  showHeroCompare(false);
  if (state.heroComparison) {
    renderHeroComparison();
    return;
  }
  el.heroCompareSummary.textContent = "Loading...";
  el.heroComparePicker.innerHTML = `<p class="subtle">Loading wiki comparison table...</p>`;
  el.heroCompareContent.innerHTML = "";
  try {
    state.heroComparison = await getJson("/api/hero-comparison");
    renderHeroComparison();
  } catch (error) {
    el.heroCompareSummary.textContent = "Table unavailable";
    el.heroComparePicker.innerHTML = `<p class="subtle">${escapeHtml(error.message)}</p>`;
  }
}

function heroLookupValue() {
  const value = el.heroDataInput.value.trim();
  if (value) return value;
  if (state.selectedPerformance?.heroName) return state.selectedPerformance.heroName;
  return state.heroes[0]?.name || "Silver";
}

function statGroupHtml(title, stats) {
  if (!stats?.length) return "";
  return `
    <section class="heroStatGroup">
      <h4>${escapeHtml(title)}</h4>
      <div class="heroStatGrid">
        ${stats.map((stat) => `
          <div class="statBox">
            <span>${escapeHtml(stat.label || stat.key)}</span>
            <strong>${escapeHtml(fmt(stat.value))}</strong>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function propertyChipsHtml(properties) {
  const chips = (properties || []).slice(0, 14).map((prop) => `
    <span class="deltaChip">${escapeHtml(prop.label)}: ${escapeHtml(prop.value)}</span>
  `);
  return chips.length ? chips.join("") : `<span class="meta">No key gameplay values exposed in the cached properties.</span>`;
}

function descriptionHtml(descriptions) {
  const values = Object.entries(descriptions || {})
    .filter(([key, value]) => key === "desc" && value)
    .map(([_key, value]) => value);
  if (!values.length) return "";
  return `<p class="heroDescription">${escapeHtml(values.join(" "))}</p>`;
}

function abilityUpgradesHtml(upgrades) {
  const items = (upgrades || []).filter((upgrade) => upgrade?.description || upgrade?.propertyUpgrades?.length);
  if (!items.length) return "";
  const maxTier = Math.max(...items.map((upgrade) => Number(upgrade.tier || 0)), 0);
  const title = maxTier ? `Upgrades ${items.length}/${maxTier}` : "Upgrades";
  const rows = items.map((upgrade) => [
    String(upgrade.tier || ""),
    upgrade.description,
    upgrade.propertyUpgrades || [],
  ]);
  const missing = [];
  for (let tier = 1; tier <= maxTier; tier += 1) {
    if (!items.some((upgrade) => Number(upgrade.tier) === tier)) missing.push(tier);
  }
  const missingText = missing.length ? `<span class="meta">Missing cached text for ${missing.join(", ")}</span>` : "";
  return `
    <div class="abilityUpgrades">
      <div class="abilityUpgradeHeader">${title}</div>
      ${rows.map(([tier, text, propertyUpgrades]) => `
        <div class="abilityUpgrade">
          <span>${tier}</span>
          <strong>
            ${text ? `<em>${escapeHtml(text)}</em>` : ""}
            ${(propertyUpgrades || []).length ? `
              <small>${propertyUpgrades.map((upgrade) => escapeHtml(upgrade)).join(" · ")}</small>
            ` : ""}
          </strong>
        </div>
      `).join("")}
      ${missingText}
    </div>
  `;
}

function linkedAbilitiesHtml(abilities) {
  const items = abilities || [];
  if (!items.length) return "";
  return `
    <div class="linkedAbilities">
      ${items.map((ability) => `
        <article class="linkedAbility">
          <div class="heroAbilityTitle">
            <strong>${escapeHtml(ability.name || ability.className || "Linked ability")}</strong>
            <span class="meta">linked</span>
          </div>
          ${descriptionHtml(ability.descriptions)}
          ${abilityUpgradesHtml(ability.upgrades)}
          <div class="combatDeltas">${propertyChipsHtml(ability.properties)}</div>
        </article>
      `).join("")}
    </div>
  `;
}

function assetCardHtml(asset, indexLabel = "") {
  return `
    <article class="heroAbilityCard">
      ${asset.image ? `<img src="${escapeHtml(asset.image)}" alt="">` : `<span class="heroAbilityIcon">${escapeHtml(indexLabel || "A")}</span>`}
      <div>
        <div class="heroAbilityTitle">
          <strong>${escapeHtml(asset.name || asset.className || "Unknown ability")}</strong>
          <span class="meta">${escapeHtml(asset.type || asset.className || "")}</span>
        </div>
        ${descriptionHtml(asset.descriptions)}
        ${abilityUpgradesHtml(asset.upgrades)}
        <div class="combatDeltas">${propertyChipsHtml(asset.properties)}</div>
        ${linkedAbilitiesHtml(asset.dependentAbilities)}
      </div>
    </article>
  `;
}

function costBonusesHtml(costBonuses) {
  const entries = Object.entries(costBonuses || {});
  if (!entries.length) return `<p class="subtle">No cost bonus table in the cached hero record.</p>`;
  return entries.map(([name, rows]) => `
    <section class="heroStatGroup">
      <h4>${escapeHtml(name)}</h4>
      <div class="costBonusGrid">
        ${(Array.isArray(rows) ? rows : []).map((row) => `
          <div class="costBonusBox">
            <span>${fmt(row.gold_threshold)} souls</span>
            <strong>${escapeHtml(fmt(row.bonus))}</strong>
          </div>
        `).join("")}
      </div>
    </section>
  `).join("");
}

function renderHeroData(hero) {
  state.selectedHeroData = hero;
  const baseStats = hero.baseStats || {};
  const scalingStats = hero.scalingStats || {};
  const hasScalingStats = Object.keys(scalingStats).length > 0;
  const rawDetails = el.heroRawToggle.checked ? `
    <section class="sectionBlock">
      <div class="sectionTitle">
        <h3>Raw Details</h3>
        <span>Cached manifest record</span>
      </div>
      <pre class="rawHeroJson">${escapeHtml(JSON.stringify({ hero: hero.raw, abilities: hero.abilities, weapons: hero.weapons }, null, 2))}</pre>
    </section>
  ` : "";

  el.heroDataSummary.textContent = `${hero.heroType || "Hero"} · complexity ${fmt(hero.complexity)} · ${hero.gunTag || hero.className}`;
  el.heroDataContent.innerHTML = `
    <section class="heroDataHero">
      ${hero.card || hero.icon ? `<img src="${escapeHtml(hero.card || hero.icon)}" alt="">` : ""}
      <div class="heroDataOverlay">
        <p class="meta">${escapeHtml(hero.className || "")}</p>
        <h2>${escapeHtml(hero.name || "Unknown hero")}</h2>
        <div class="statPills">
          <span class="pill">Type: <strong>${escapeHtml(hero.heroType || "-")}</strong></span>
          <span class="pill">Weapon: <strong>${escapeHtml(hero.gunTag || "-")}</strong></span>
          <span class="pill">Complexity: <strong>${escapeHtml(fmt(hero.complexity))}</strong></span>
        </div>
        ${descriptionHtml(hero.description)}
      </div>
    </section>
    <section class="sectionBlock">
      <div class="sectionTitle">
        <h3>Base Stats</h3>
        <span>Starting hero values</span>
      </div>
      <div class="heroStats">
        ${["Vitality", "Weapon", "Spirit", "Mobility", "Other"].map((group) => statGroupHtml(group, baseStats[group])).join("")}
      </div>
    </section>
    <section class="sectionBlock">
      <div class="sectionTitle">
        <h3>Abilities</h3>
        <span>${fmt(hero.abilities?.length || 0)} signature abilities</span>
      </div>
      <div class="heroAbilityGrid">
        ${(hero.abilities || []).map((ability, index) => assetCardHtml(ability, String(index + 1))).join("") || `<p class="subtle">No signature abilities found in the cached hero record.</p>`}
      </div>
    </section>
    <section class="sectionBlock">
      <div class="sectionTitle">
        <h3>Weapons</h3>
        <span>Primary and melee records</span>
      </div>
      <div class="heroAbilityGrid">
        ${(hero.weapons || []).map((weapon) => assetCardHtml(weapon, "W")).join("") || `<p class="subtle">No weapon records found in the cached hero record.</p>`}
      </div>
    </section>
    <section class="sectionBlock">
      <div class="sectionTitle">
        <h3>Scaling</h3>
        <span>${hasScalingStats ? "Hero scaling stats" : "Cost bonus thresholds"}</span>
      </div>
      <div class="heroStats">
        ${hasScalingStats ? Object.entries(scalingStats).map(([group, stats]) => statGroupHtml(group, stats)).join("") : costBonusesHtml(hero.costBonuses)}
      </div>
    </section>
    ${rawDetails}
  `;
}

async function loadHeroData() {
  showHeroData(false);
  const hero = heroLookupValue();
  el.heroDataInput.value = hero;
  el.heroDataSummary.textContent = "Loading...";
  el.heroDataContent.innerHTML = `<section class="sectionBlock"><p class="subtle">Loading ${escapeHtml(hero)} from the cached asset manifest...</p></section>`;
  try {
    renderHeroData(await getJson(`/api/heroes/${encodeURIComponent(hero)}`));
  } catch (error) {
    el.heroDataSummary.textContent = "Hero not found";
    el.heroDataContent.innerHTML = `<section class="sectionBlock"><p class="subtle">${escapeHtml(error.message)}</p></section>`;
  }
}

function itemLabParams(mode) {
  const params = new URLSearchParams({
    mode,
    hero: el.itemHeroInput.value.trim(),
    enemies: el.itemEnemiesInput.value.trim(),
    enemyScope: el.enemyScopeInput.value,
    ownedItems: el.ownedItemsInput.value.trim(),
    item: el.itemSearchInput.value.trim(),
    minMatches: numericInputValue(el.itemMinMatchesInput) || "20",
    limit: "40",
  });
  const beforeS = secondsFromMinuteValue(el.gameMinuteInput);
  if (beforeS) params.set("beforeS", beforeS);
  if (el.includeAbilitiesInput.checked) params.set("includeAbilities", "1");
  return params;
}

function itemEvidenceParams(item) {
  const params = itemLabParams("evidence");
  params.set("itemId", String(item.itemId));
  params.delete("item");
  params.set("limit", "120");
  return params;
}

function itemConfidenceText(item) {
  return `${fmt(item.buyers)} samples · ${fmt(item.wins)} wins · ${fmt(item.wilsonLow)}-${fmt(item.wilsonHigh)}% Wilson`;
}

function renderItemResults(payload, mode) {
  const context = payload.context || {};
  el.itemResults.dataset.loaded = "1";
  el.itemResultsTitle.textContent = mode === "recommend" ? "Recommendations" : "Discovery";
  el.itemResultCount.textContent = `${fmt(payload.totalItems)} matching items`;
  el.itemLabSummary.textContent = `${fmt(context.players)} player contexts · ${fmt(context.baselineWinRate)}% baseline · by ${context.beforeText || "-"}`;
  if (!payload.items?.length) {
    state.itemResultsById = new Map();
    el.itemResults.innerHTML = `<p class="subtle">No item results match the current filters.</p>`;
    el.itemEvidence.classList.add("hidden");
    return;
  }
  state.itemResultsById = new Map(payload.items.map((item) => [String(item.itemId), item]));
  el.itemEvidence.classList.add("hidden");
  el.itemEvidence.innerHTML = "";
  el.itemResults.innerHTML = payload.items.map((item) => `
    <article class="itemResult" data-item-id="${item.itemId}">
      <img src="${item.asset?.image || ""}" alt="">
      <div class="itemResultMain">
        <strong>${item.itemName}</strong>
        <span class="meta">${itemConfidenceText(item)}</span>
        <span class="meta">Pick ${fmt(item.pickRate)}% · avg buy ${item.avgBuyText}</span>
      </div>
      <div class="itemResultScore">
        <strong>${fmt(item.winRate)}%</strong>
        <span class="${Number(item.lift) >= 0 ? "win" : "loss"}">${Number(item.lift) >= 0 ? "+" : ""}${fmt(item.lift)}%</span>
        <button class="evidenceButton" type="button" data-item-id="${item.itemId}">Evidence</button>
      </div>
    </article>
  `).join("");
}

async function loadItemMatchups(mode = "study") {
  showItemLab(false);
  el.itemResultCount.textContent = "Loading...";
  el.itemResults.innerHTML = `<p class="subtle">Calculating from local matches...</p>`;
  const payload = await getJson(`/api/item-matchups?${itemLabParams(mode).toString()}`);
  renderItemResults(payload, mode);
}

function enemyEvidenceText(row) {
  const enemies = row.enemies || [];
  if (!enemies.length) return "-";
  return enemies.map((enemy) => {
    const kda = `${fmt(enemy.kills)}/${fmt(enemy.deaths)}/${fmt(enemy.assists)}`;
    return `${enemy.heroName || "Enemy"} ${kda}`;
  }).join(", ");
}

function renderEvidenceRows(payload, item, target = el.itemEvidence) {
  target.classList.remove("hidden");
  const rows = payload.items || [];
  if (!rows.length) {
    target.innerHTML = `<p class="subtle">No backing matches found for ${escapeHtml(item.itemName)}.</p>`;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  target.innerHTML = `
    <div class="evidenceHeader">
      <div>
        <h3>Matches Behind This</h3>
        <p class="meta">${escapeHtml(item.itemName)} · ${fmt(payload.totalMatched)} records</p>
      </div>
    </div>
    <div class="evidenceTable">
      <div class="evidenceRow evidenceHead">
        <span>Result</span>
        <span>Match</span>
        <span>Buy</span>
        <span>Duration</span>
        <span>Player</span>
        <span>Enemy</span>
        <span>Rank</span>
      </div>
      ${rows.map((row) => `
        <button class="evidenceRow" type="button" data-match-id="${row.matchId}" data-player-slot="${row.playerSlot}">
          <span class="${row.won ? "win" : "loss"}">${row.won ? "Win" : "Loss"}</span>
          <span>${row.matchId}</span>
          <span>${row.buyTimeText}</span>
          <span>${row.durationText}</span>
          <span>${row.heroName || "Hero"} ${fmt(row.kills)}/${fmt(row.deaths)}/${fmt(row.assists)} · ${fmt(row.netWorth)} NW</span>
          <span>${enemyEvidenceText(row)}</span>
          <span>${rankText(row.averageBadge) || "-"}</span>
        </button>
      `).join("")}
    </div>
  `;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  target.querySelectorAll(".evidenceRow[data-match-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const matchId = button.dataset.matchId;
        const playerSlot = button.dataset.playerSlot;
        state.selectedPerformance = null;
        state.selectedPlayerSlot = playerSlot;
        state.selectedMatch = await getJson(`/api/matches/${matchId}`);
        el.heroData.classList.add("hidden");
        el.itemLab.classList.add("hidden");
        renderMatch();
      } catch (error) {
        target.insertAdjacentHTML("afterbegin", `<p class="subtle">${escapeHtml(error.message)}</p>`);
      }
    });
  });
}

async function loadItemEvidence(item) {
  if (!item) return;
  el.itemEvidence.classList.remove("hidden");
  el.itemEvidence.innerHTML = `<p class="subtle">Loading backing matches for ${item.itemName}...</p>`;
  el.itemEvidence.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const payload = await getJson(`/api/item-evidence?${itemEvidenceParams(item).toString()}`);
    renderEvidenceRows(payload, item, el.itemEvidence);
  } catch (error) {
    el.itemEvidence.innerHTML = `<p class="subtle">${escapeHtml(error.message)}</p>`;
  }
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
  el.heroData.classList.add("hidden");
  el.matchDetail.classList.remove("hidden");
  el.featuredHeroCard.src = player.hero?.card || player.hero?.icon || "";
  el.matchMeta.textContent = `Match ${match.match_id} · ${match.start_time || "unknown start"} · ${match.durationText} · ${match.game_mode || ""} ${match.match_mode || ""} · ${rankMeta(match.averageBadge)}`;
  el.featuredTitle.textContent = `${player.hero_name || "Unknown hero"} standout performance`;
  el.featuredStats.innerHTML = [
    ["Score", fmt(player.score)],
    ["Percentile", pct(player.percentile)],
    ["Match rank", rankText(match.averageBadge) || "Unavailable"],
    ["K/D/A", `${fmt(player.kills)}/${fmt(player.deaths)}/${fmt(player.assists)}`],
    ["KDA ratio", fmt(player.kdaRatio)],
    ["Net worth", fmt(player.net_worth)],
    ["Damage", fmt(player.finalStats?.player_damage)],
    ["Result", player.won ? "Win" : "Loss"],
    ["Why", (player.reasons || []).join(", ") || "strong score"],
  ].map(([label, value]) => `<span class="pill">${label}: <strong>${value}</strong></span>`).join("");
  renderSaveMatchState();

  renderScoreboard(payload.players);
  renderMatchItemPlayerOptions(payload.players);
  loadAbilitySheet();
  loadMatchItemLab();
  renderSelectedPlayer(player);
}

function renderSaveMatchState(message = "") {
  const match = state.selectedMatch?.match;
  const isSaved = Boolean(match?.saved);
  el.saveMatchButton.disabled = !match || isSaved;
  el.saveMatchButton.textContent = isSaved ? "Saved Match" : "Save Match";
  el.saveMatchStatus.textContent = message || (isSaved ? "Kept across fresh pulls" : "Save this match across fresh pulls");
}

async function saveSelectedMatch() {
  const match = state.selectedMatch?.match;
  if (!match?.match_id) return;
  el.saveMatchButton.disabled = true;
  el.saveMatchStatus.textContent = "Saving...";
  try {
    await postJson(`/api/matches/${match.match_id}/save`);
    match.saved = true;
    renderSaveMatchState("Saved to data/deadlock-saved");
  } catch (error) {
    el.saveMatchButton.disabled = false;
    el.saveMatchStatus.textContent = error.message;
  }
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

    for (const player of teamPlayers.slice().sort(comparePlayersForScoreboard)) {
      column.appendChild(renderPlayerRow(player));
    }

    el.scoreboard.appendChild(column);
  }
}

function metricCellHtml(metric) {
  const notes = metric?.notes || [];
  const title = notes.length ? ` title="${escapeHtml(notes.join(" · "))}"` : "";
  return `<td${title}>${escapeHtml(metric?.value || "-")}</td>`;
}

function metricSortValue(metric) {
  const value = String(metric?.value || "");
  const number = Number(value.match(/[-+]?\d+(?:\.\d+)?/)?.[0]);
  return Number.isFinite(number) ? number : -Infinity;
}

function abilitySheetSortValue(row, key) {
  if (key === "team") return row.team || "";
  if (key === "hero") return row.heroName || "";
  if (key === "player") return Number(row.playerSlot || 0);
  if (key === "ability") return row.abilityName || "";
  if (key === "rank") return Number(row.rank || 0);
  if (["totalDamage", "cooldown", "range", "radius"].includes(key)) return metricSortValue(row[key]);
  return "";
}

function sortAbilitySheetRows(rows) {
  const { key, direction } = state.abilitySheetSort;
  const multiplier = direction === "desc" ? -1 : 1;
  return rows.slice().sort((a, b) => {
    const valueA = abilitySheetSortValue(a, key);
    const valueB = abilitySheetSortValue(b, key);
    if (typeof valueA === "number" || typeof valueB === "number") {
      return ((Number(valueA) || 0) - (Number(valueB) || 0)) * multiplier
        || String(a.heroName || "").localeCompare(String(b.heroName || ""))
        || String(a.abilityName || "").localeCompare(String(b.abilityName || ""));
    }
    return String(valueA).localeCompare(String(valueB)) * multiplier
      || Number(a.playerSlot || 0) - Number(b.playerSlot || 0);
  });
}

function sortHeaderHtml(key, label) {
  const active = state.abilitySheetSort.key === key;
  const marker = active ? (state.abilitySheetSort.direction === "asc" ? " ▲" : " ▼") : "";
  return `<button class="sheetSortButton${active ? " active" : ""}" type="button" data-sort-key="${key}">${label}${marker}</button>`;
}

function abilityTooltipHtml(ability) {
  if (!ability) return "";
  return `
    <div class="abilityTooltip">
      <strong>${escapeHtml(ability.name || ability.className || "Ability")}</strong>
      ${descriptionHtml(ability.descriptions)}
      ${abilityUpgradesHtml(ability.upgrades)}
      <div class="combatDeltas">${propertyChipsHtml(ability.properties)}</div>
    </div>
  `;
}

function renderAbilitySheet(payload) {
  state.abilitySheet = payload;
  const rows = sortAbilitySheetRows(payload.rows || []);
  el.abilitySheetSummary.textContent = `${fmt(rows.length)} ability records · ${payload.timeText} · scaling ${payload.includeScaling ? "on" : "off"}`;
  if (!rows.length) {
    el.abilitySheet.innerHTML = `<p class="subtle">No ability rows found for this match.</p>`;
    return;
  }
  el.abilitySheet.innerHTML = `
    <p class="subtle">${escapeHtml(payload.note || "")}</p>
    <div class="abilitySheetTableWrap">
      <table class="abilitySheetTable">
        <thead>
          <tr>
            <th>${sortHeaderHtml("team", "Team")}</th>
            <th>${sortHeaderHtml("hero", "Hero")}</th>
            <th>${sortHeaderHtml("player", "Slot")}</th>
            <th>${sortHeaderHtml("ability", "Ability")}</th>
            <th>${sortHeaderHtml("rank", "Rank")}</th>
            <th>${sortHeaderHtml("totalDamage", "Total Damage")}</th>
            <th>${sortHeaderHtml("cooldown", "Cooldown")}</th>
            <th>${sortHeaderHtml("range", "Range")}</th>
            <th>${sortHeaderHtml("radius", "Radius")}</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr class="${row.unlocked ? "" : "lockedAbility"}">
              <td>${escapeHtml(row.team || "-")}</td>
              <td>
                <span class="sheetHero">
                  <img src="${escapeHtml(row.hero?.icon || "")}" alt="">
                  ${escapeHtml(row.heroName || "Hero")}
                </span>
              </td>
              <td>${escapeHtml(row.playerSlot)}</td>
              <td>
                <span class="sheetAbility">
                  ${escapeHtml(row.abilityName || "Ability")}
                  ${abilityTooltipHtml(row.ability)}
                </span>
              </td>
              <td>${row.unlocked ? `${fmt(row.rank)} · ${fmt(row.upgradeTiers)} upgrades` : "locked"}</td>
              ${metricCellHtml(row.totalDamage)}
              ${metricCellHtml(row.cooldown)}
              ${metricCellHtml(row.range)}
              ${metricCellHtml(row.radius)}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function sortAbilitySheetBy(key) {
  if (state.abilitySheetSort.key === key) {
    state.abilitySheetSort.direction = state.abilitySheetSort.direction === "asc" ? "desc" : "asc";
  } else {
    state.abilitySheetSort = {
      key,
      direction: ["totalDamage", "cooldown", "range", "radius", "rank"].includes(key) ? "desc" : "asc",
    };
  }
  if (state.abilitySheet) renderAbilitySheet(state.abilitySheet);
}

function updateAbilitySheetCollapsed() {
  el.abilitySheetBody.classList.toggle("hidden", state.abilitySheetCollapsed);
  el.toggleAbilitySheetButton.textContent = state.abilitySheetCollapsed ? "Expand" : "Minimize";
}

async function loadAbilitySheet() {
  const matchId = state.selectedMatch?.match?.match_id;
  if (!matchId) return;
  const params = new URLSearchParams({
    timeS: secondsFromMinuteValue(el.abilitySheetMinuteInput) || "720",
  });
  if (el.abilitySheetScalingInput.checked) params.set("includeScaling", "1");
  el.abilitySheetSummary.textContent = "Loading...";
  el.abilitySheet.innerHTML = `<p class="subtle">Building ability sheet...</p>`;
  try {
    renderAbilitySheet(await getJson(`/api/matches/${matchId}/ability-sheet?${params.toString()}`));
  } catch (error) {
    el.abilitySheetSummary.textContent = "Unable to load ability sheet";
    el.abilitySheet.innerHTML = `<p class="subtle">${escapeHtml(error.message)}</p>`;
  }
}

function renderMatchItemPlayerOptions(players) {
  el.matchItemPlayerInput.innerHTML = (players || [])
    .slice()
    .sort(comparePlayersBySlot)
    .map((player) => `
      <option value="${escapeHtml(player.player_slot)}">
        ${escapeHtml(player.hero_name || "Hero")} · slot ${escapeHtml(player.player_slot)} · ${escapeHtml(player.team || "team")}
      </option>
    `).join("");
  el.matchItemPlayerInput.value = String(state.selectedPlayerSlot ?? players?.[0]?.player_slot ?? "");
}

function matchItemLabParams() {
  const params = new URLSearchParams({
    playerSlot: el.matchItemPlayerInput.value || String(state.selectedPlayerSlot || ""),
    timeS: secondsFromMinuteValue(el.matchItemMinuteInput) || secondsFromMinuteValue(el.abilitySheetMinuteInput) || "720",
    minMatches: numericInputValue(el.matchItemMinMatchesInput) || "20",
    limit: "40",
  });
  if (el.matchItemIncludeAbilitiesInput.checked) params.set("includeAbilities", "1");
  return params;
}

function matchItemHeroChip(hero, fallback = "Hero") {
  const name = hero?.heroName || hero?.name || fallback;
  const icon = hero?.asset?.icon || hero?.hero?.icon || "";
  return `
    <span class="matchContextChip">
      ${icon ? `<img src="${escapeHtml(icon)}" alt="">` : ""}
      ${escapeHtml(name)}
    </span>
  `;
}

function matchItemContextGroup(title, html, emptyText = "None") {
  return `
    <div class="matchContextGroup">
      <span>${escapeHtml(title)}</span>
      <div>${html || `<span class="deltaChip">${escapeHtml(emptyText)}</span>`}</div>
    </div>
  `;
}

function renderMatchItemContext(payload) {
  const matchContext = payload.matchContext || {};
  const context = payload.context || {};
  const ownedItems = matchContext.ownedItems || [];
  el.matchItemContext.innerHTML = `
    ${matchItemContextGroup("Target", matchItemHeroChip(matchContext.hero, "Target"))}
    ${matchItemContextGroup("Allies", (matchContext.allies || []).map((hero) => matchItemHeroChip(hero, "Ally")).join(""))}
    ${matchItemContextGroup("Enemies", (matchContext.enemies || []).map((hero) => matchItemHeroChip(hero, "Enemy")).join(""))}
    ${matchItemContextGroup("Owned", ownedItems.map((item) => `
      <span class="matchContextChip">
        ${item.asset?.image ? `<img src="${escapeHtml(item.asset.image)}" alt="">` : ""}
        ${escapeHtml(item.itemName || `Item ${item.itemId}`)}
      </span>
    `).join(""))}
    ${matchItemContextGroup("Used", `
      <span class="deltaChip">${escapeHtml(context.fallbackLevel || "Exact")}</span>
      <span class="deltaChip">${fmt(context.players)} contexts</span>
      <span class="deltaChip">${fmt(context.baselineWinRate)}% baseline</span>
    `)}
  `;
}

function renderMatchItemResults(payload) {
  state.matchItemLab = payload;
  state.matchItemResultsById = new Map((payload.items || []).map((item) => [String(item.itemId), item]));
  const context = payload.context || {};
  el.matchItemLabSummary.textContent = `${context.fallbackLevel || "Exact"} · ${fmt(context.players)} contexts · ${fmt(context.baselineWinRate)}% baseline · by ${context.beforeText || "-"}`;
  renderMatchItemContext(payload);
  el.matchItemEvidence.classList.add("hidden");
  el.matchItemEvidence.innerHTML = "";
  if (!payload.items?.length) {
    el.matchItemResults.innerHTML = `<p class="subtle">No recommendations matched this match context.</p>`;
    return;
  }
  el.matchItemResults.innerHTML = payload.items.map((item) => `
    <article class="itemResult" data-item-id="${item.itemId}">
      <img src="${escapeHtml(item.asset?.image || "")}" alt="">
      <div class="itemResultMain">
        <strong>${escapeHtml(item.itemName)}</strong>
        <span class="meta">${itemConfidenceText(item)}</span>
        <span class="meta">Pick ${fmt(item.pickRate)}% · avg buy ${item.avgBuyText} · ${escapeHtml(context.fallbackLevel || "Exact")}</span>
      </div>
      <div class="itemResultScore">
        <strong>${fmt(item.winRate)}%</strong>
        <span class="${Number(item.lift) >= 0 ? "win" : "loss"}">${Number(item.lift) >= 0 ? "+" : ""}${fmt(item.lift)}%</span>
        <button class="matchEvidenceButton evidenceButton" type="button" data-item-id="${item.itemId}">Evidence</button>
      </div>
    </article>
  `).join("");
}

async function loadMatchItemLab() {
  const matchId = state.selectedMatch?.match?.match_id;
  if (!matchId) return;
  if (!el.matchItemPlayerInput.value && state.selectedPlayerSlot != null) {
    el.matchItemPlayerInput.value = String(state.selectedPlayerSlot);
  }
  el.matchItemLabSummary.textContent = "Loading...";
  el.matchItemContext.innerHTML = "";
  el.matchItemResults.innerHTML = `<p class="subtle">Calculating recommendations from this match...</p>`;
  try {
    renderMatchItemResults(await getJson(`/api/matches/${matchId}/item-lab?${matchItemLabParams().toString()}`));
  } catch (error) {
    el.matchItemLabSummary.textContent = "Unable to load Match Item Lab";
    el.matchItemResults.innerHTML = `<p class="subtle">${escapeHtml(error.message)}</p>`;
  }
}

function matchItemEvidenceParams(item) {
  const context = state.matchItemLab?.context || {};
  const params = new URLSearchParams({
    mode: "evidence",
    hero: context.hero || "",
    enemies: (context.enemies || []).join(","),
    allies: (context.allies || []).join(","),
    ownedItems: (context.ownedItems || []).join(","),
    enemyScope: context.enemyScope || "team",
    itemId: String(item.itemId),
    limit: "120",
  });
  if (context.beforeS != null) params.set("beforeS", String(context.beforeS));
  if (el.matchItemIncludeAbilitiesInput.checked) params.set("includeAbilities", "1");
  return params;
}

async function loadMatchItemEvidence(item) {
  if (!item) return;
  el.matchItemEvidence.classList.remove("hidden");
  el.matchItemEvidence.innerHTML = `<p class="subtle">Loading backing matches for ${escapeHtml(item.itemName)}...</p>`;
  el.matchItemEvidence.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const payload = await getJson(`/api/item-evidence?${matchItemEvidenceParams(item).toString()}`);
    renderEvidenceRows(payload, item, el.matchItemEvidence);
  } catch (error) {
    el.matchItemEvidence.innerHTML = `<p class="subtle">${escapeHtml(error.message)}</p>`;
  }
}

function updateMatchItemLabCollapsed() {
  el.matchItemLabBody.classList.toggle("hidden", state.matchItemLabCollapsed);
  el.toggleMatchItemLabButton.textContent = state.matchItemLabCollapsed ? "Expand" : "Minimize";
}

function laneLabel(player) {
  const lane = Number(player?.assigned_lane ?? player?.assignedLane);
  if (!Number.isFinite(lane) || lane <= 0) return "Lane ?";
  return `Lane ${lane}`;
}

function enemyLaneText(perf) {
  const heroes = (perf.enemyLaneHeroes || [])
    .map((hero) => hero.heroName || hero.name)
    .filter(Boolean);
  if (!heroes.length) return "";
  return `${laneLabel(perf)} vs ${heroes.join(", ")}`;
}

function comparePlayersByLane(a, b) {
  const laneA = Number(a.assigned_lane);
  const laneB = Number(b.assigned_lane);
  const safeLaneA = Number.isFinite(laneA) ? laneA : Number.MAX_SAFE_INTEGER;
  const safeLaneB = Number.isFinite(laneB) ? laneB : Number.MAX_SAFE_INTEGER;
  return safeLaneA - safeLaneB || Number(a.player_slot) - Number(b.player_slot);
}

function comparePlayersByScore(a, b) {
  return Number(b.score) - Number(a.score) || Number(a.player_slot) - Number(b.player_slot);
}

function comparePlayersBySlot(a, b) {
  return Number(a.player_slot) - Number(b.player_slot);
}

function comparePlayersForScoreboard(a, b) {
  if (state.scoreboardSort === "score") return comparePlayersByScore(a, b);
  if (state.scoreboardSort === "slot") return comparePlayersBySlot(a, b);
  return comparePlayersByLane(a, b);
}

function renderPlayerRow(player) {
  const button = document.createElement("button");
  button.className = "playerRow";
  if (Number(player.player_slot) === Number(state.selectedPlayerSlot)) button.classList.add("active");
  button.innerHTML = `
    <img src="${player.hero?.icon || ""}" alt="">
    <span>
      <strong>${player.hero_name || "Unknown hero"}</strong>
      <span class="meta">${player.team || "team"} · ${laneLabel(player)} · ${fmt(player.kills)}/${fmt(player.deaths)}/${fmt(player.assists)} · ${fmt(player.net_worth)} NW</span>
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

  renderChart(player);
  renderFullTimeline(player, shopItems, abilityItems);
  renderFinalStats(player);
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

function fullTimelineChip(label, className = "") {
  return `<span class="deltaChip ${className}">${label}</span>`;
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
        item.sold_time_s && !hasSeparateSellEvent ? fullTimelineChip(`sold ${mmss(item.sold_time_s)}`, "soldChip") : "",
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
      noIcon: true,
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

function sampleTime(sample) {
  return Number(sample?.time_stamp_s || 0);
}

function sampleAtOrBefore(samples, time) {
  let found = null;
  for (const sample of samples) {
    if (sampleTime(sample) <= time) {
      found = sample;
    } else {
      break;
    }
  }
  return found;
}

function summaryTimelineEvents(player) {
  const samples = [...(player.stats || [])].sort((a, b) => sampleTime(a) - sampleTime(b));
  if (!samples.length) return [];

  const maxTime = Math.max(...samples.map(sampleTime));
  const events = [];
  for (let startTime = 0; startTime < maxTime; startTime += SUMMARY_WINDOW_SECONDS) {
    const endTime = Math.min(startTime + SUMMARY_WINDOW_SECONDS, maxTime);
    const previous = sampleAtOrBefore(samples, startTime) || {};
    const current = sampleAtOrBefore(samples, endTime) || samples[samples.length - 1];
    const kills = statDelta(current, previous, "kills");
    const deaths = statDelta(current, previous, "deaths");
    const assists = statDelta(current, previous, "assists");
    const netWorth = Number(current?.net_worth || 0);
    const netWorthGain = statDelta(current, previous, "net_worth");

    events.push({
      type: "summary",
      lane: "summary",
      noIcon: true,
      startTime,
      endTime,
      time: endTime,
      timeLabel: `${mmss(startTime)}-${mmss(endTime)}`,
      title: `Total ${fmt(current?.kills || 0)}/${fmt(current?.deaths || 0)}/${fmt(current?.assists || 0)} KDA`,
      chips: [
        fullTimelineChip(`window +${fmt(kills)}/${fmt(deaths)}/${fmt(assists)} KDA`),
        fullTimelineChip(`${fmt(netWorth)} NW`),
        netWorthGain ? fullTimelineChip(`+${fmt(netWorthGain)} NW`) : "",
      ].filter(Boolean).join(""),
    });
  }
  return events;
}

function timelineEventCard(event) {
  return `
    <div class="timelineEvent ${event.type}Event ${event.lane === "window" ? "windowEvent" : ""} ${event.lane === "summary" ? "summaryEvent" : ""} ${event.typeClass || ""}">
      <span class="combatTime">${event.timeLabel || mmss(event.time)}</span>
      ${event.noIcon ? "" : event.image ? `<img src="${event.image}" alt="">` : `<span class="timelineIcon">${event.iconLabel || event.type}</span>`}
      <span>
        <strong>${event.title}</strong>
        <span class="combatDeltas">${event.chips}</span>
      </span>
    </div>
  `;
}

function timelineRows(events) {
  const mainEvents = events.filter((event) => event.lane !== "window" && event.lane !== "summary");
  const windowEvents = events.filter((event) => event.lane === "window");
  const summaryEvents = events.filter((event) => event.lane === "summary");
  const rows = (summaryEvents.length ? summaryEvents : windowEvents).map((event) => ({
    startTime: event.startTime ?? event.time,
    endTime: event.endTime ?? event.time,
    main: [],
    windows: event.lane === "window" ? [event] : [],
    summaries: event.lane === "summary" ? [event] : [],
  }));

  for (const event of windowEvents) {
    if (!summaryEvents.length) continue;
    const matchingRow = rows.find((row) => event.time >= row.startTime && event.time <= row.endTime);
    if (matchingRow) {
      matchingRow.windows.push(event);
    } else {
      rows.push({ startTime: event.time, endTime: event.time, main: [], windows: [event], summaries: [] });
    }
  }

  for (const event of mainEvents) {
    const matchingRow = rows.find((row) => event.time >= row.startTime && event.time <= row.endTime);
    if (matchingRow) {
      matchingRow.main.push(event);
    } else {
      rows.push({ startTime: event.time, endTime: event.time, main: [event], windows: [], summaries: [] });
    }
  }
  return rows
    .map((row) => ({
      ...row,
      main: row.main.sort((a, b) => a.time - b.time || String(a.type).localeCompare(String(b.type))),
      windows: row.windows.sort((a, b) => a.time - b.time),
      summaries: row.summaries.sort((a, b) => a.time - b.time),
    }))
    .sort((a, b) => a.startTime - b.startTime);
}

function groupedMainTimelineCards(events) {
  const groups = [];
  for (const event of events) {
    const group = groups.find((existing) => shouldGroupTimelineEvents(existing, event));
    if (group) {
      group.events.push(event);
      group.endTime = Math.max(group.endTime, Number(event.time || 0));
    } else {
      groups.push({ time: event.time, endTime: Number(event.time || 0), events: [event] });
    }
  }

  return groups.map((group) => `
    <div class="timelineMainGroup${group.events.length > 1 ? " sameTimeGroup" : ""}" style="--timeline-columns: ${group.events.length}">
      ${group.events.map(timelineEventCard).join("")}
    </div>
  `).join("");
}

function shouldGroupTimelineEvents(group, event) {
  const eventTime = Number(event.time || 0);
  if (group.time === event.time) return true;
  const isNearbyItemEvent = event.type === "item" && group.events.every((item) => item.type === "item");
  return isNearbyItemEvent && Math.abs(eventTime - group.endTime) <= GROUP_NEARBY_ITEM_EVENT_SECONDS;
}

function renderFullTimeline(player, shopItems, abilityItems) {
  const allEvents = [
    ...itemTimelineEvents(shopItems),
    ...abilityTimelineEvents(abilityItems),
    ...killDeathTimelineEvents(player),
    ...windowTimelineEvents(player),
    ...summaryTimelineEvents(player),
  ].sort((a, b) => a.time - b.time || String(a.type).localeCompare(String(b.type)));
  const events = allEvents.filter((event) => event.lane === "window" || event.lane === "summary" || state.timelineEventTypes.has(event.type));

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
      <div class="timelineLane summaryLane">${row.summaries.map(timelineEventCard).join("")}</div>
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
el.enemyLaneHeroInput.addEventListener("input", debounce(saveFiltersAndLoadPerformances));
el.savedOnlyInput.addEventListener("change", saveFiltersAndLoadPerformances);
el.scoreboardSortInput.addEventListener("change", () => {
  state.scoreboardSort = el.scoreboardSortInput.value;
  saveFilters();
  if (state.selectedMatch?.players) renderScoreboard(state.selectedMatch.players);
});
el.loadAbilitySheetButton.addEventListener("click", loadAbilitySheet);
el.abilitySheetMinuteInput.addEventListener("change", loadAbilitySheet);
el.abilitySheetScalingInput.addEventListener("change", loadAbilitySheet);
el.toggleAbilitySheetButton.addEventListener("click", () => {
  state.abilitySheetCollapsed = !state.abilitySheetCollapsed;
  updateAbilitySheetCollapsed();
});
el.abilitySheet.addEventListener("click", (event) => {
  const button = event.target.closest(".sheetSortButton");
  if (!button) return;
  sortAbilitySheetBy(button.dataset.sortKey);
});
el.loadMatchItemLabButton.addEventListener("click", loadMatchItemLab);
el.matchItemPlayerInput.addEventListener("change", loadMatchItemLab);
el.matchItemMinuteInput.addEventListener("change", loadMatchItemLab);
el.matchItemMinMatchesInput.addEventListener("change", loadMatchItemLab);
el.matchItemIncludeAbilitiesInput.addEventListener("change", loadMatchItemLab);
el.toggleMatchItemLabButton.addEventListener("click", () => {
  state.matchItemLabCollapsed = !state.matchItemLabCollapsed;
  updateMatchItemLabCollapsed();
});
el.matchItemResults.addEventListener("click", (event) => {
  const button = event.target.closest(".matchEvidenceButton");
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  loadMatchItemEvidence(state.matchItemResultsById.get(button.dataset.itemId));
});
el.refreshButton.addEventListener("click", loadPerformances);
el.saveMatchButton.addEventListener("click", saveSelectedMatch);
el.heroDataButton.addEventListener("click", showHeroData);
el.heroCompareButton.addEventListener("click", showHeroCompare);
el.loadHeroDataButton.addEventListener("click", loadHeroData);
el.heroDataInput.addEventListener("change", loadHeroData);
el.heroDataInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") loadHeroData();
});
el.heroRawToggle.addEventListener("change", () => {
  if (state.selectedHeroData) renderHeroData(state.selectedHeroData);
});
el.heroCompareSearchInput.addEventListener("input", debounce(renderHeroComparePicker, 120));
el.heroCompareSortInput.addEventListener("change", () => {
  state.heroComparisonSort.key = el.heroCompareSortInput.value;
  saveHeroCompareSettings();
  renderHeroCompareContent();
});
el.heroCompareSortDirectionButton.addEventListener("click", () => {
  state.heroComparisonSort.direction = state.heroComparisonSort.direction === "asc" ? "desc" : "asc";
  saveHeroCompareSettings();
  renderHeroCompareControls();
  renderHeroCompareContent();
});
el.heroComparePicker.addEventListener("change", (event) => {
  const input = event.target.closest("input[type='checkbox']");
  if (!input) return;
  if (input.checked && state.selectedHeroComparisonIds.size >= HERO_COMPARE_LIMIT) {
    input.checked = false;
    return;
  }
  if (input.checked) {
    state.selectedHeroComparisonIds.add(input.value);
  } else {
    state.selectedHeroComparisonIds.delete(input.value);
  }
  saveHeroCompareSettings();
  renderHeroComparePicker();
  renderHeroCompareContent();
});
el.heroCompareColumnPicker.addEventListener("change", (event) => {
  const input = event.target.closest("input[type='checkbox']");
  if (!input) return;
  if (input.checked) {
    state.selectedHeroComparisonColumns.add(input.value);
  } else {
    state.selectedHeroComparisonColumns.delete(input.value);
  }
  if (!state.selectedHeroComparisonColumns.has(state.heroComparisonSort.key)) {
    state.heroComparisonSort.key = state.selectedHeroComparisonColumns.values().next().value || "hero";
  }
  saveHeroCompareSettings();
  renderHeroCompareControls();
  renderHeroCompareContent();
});
el.heroCompareContent.addEventListener("click", (event) => {
  const button = event.target.closest(".heroCompareStatSort");
  if (!button) return;
  const column = button.dataset.column;
  if (state.heroComparisonSort.key === column) {
    state.heroComparisonSort.direction = state.heroComparisonSort.direction === "asc" ? "desc" : "asc";
  } else {
    state.heroComparisonSort.key = column;
    state.heroComparisonSort.direction = "desc";
  }
  saveHeroCompareSettings();
  renderHeroCompareControls();
  renderHeroCompareContent();
});
el.clearHeroCompareButton.addEventListener("click", () => {
  state.selectedHeroComparisonIds.clear();
  saveHeroCompareSettings();
  renderHeroComparePicker();
  renderHeroCompareContent();
});
el.itemLabButton.addEventListener("click", showItemLab);
el.itemResults.addEventListener("click", (event) => {
  const button = event.target.closest(".evidenceButton");
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  loadItemEvidence(state.itemResultsById.get(button.dataset.itemId));
});
el.discoverItemsButton.addEventListener("click", () => loadItemMatchups("study"));
el.recommendItemsButton.addEventListener("click", () => loadItemMatchups("recommend"));

loadSavedFilters();
loadHeroCompareSettings();

loadHeroList()
  .catch((_error) => {
    state.heroes = [];
  });

loadSummary()
  .then(loadPerformances)
  .catch((error) => {
    el.datasetSummary.textContent = error.message;
    el.performanceList.innerHTML = `<p class="subtle">${error.message}</p>`;
  });
