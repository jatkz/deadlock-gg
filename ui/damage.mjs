import { AP_COSTS, number, progression, buildStats, weaponStats, weaponDamage, propertyValue, damageProperties, damageTaken, impact } from './damage-engine.mjs';
const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = value => Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
const KEY = 'deadlockDamageCalculatorV1';
const FIELDS = ['hero','boons','extraSpirit','extraWeapon','spiritOverride','health','barrier','bulletResist','spiritResist','bulletShred','spiritShred','falloff','flatBullet','headMultiplier','bulletAmp','spiritAmp'];
let data, hero, abilities = [], selected = new Set(), shop = [];
const input = () => Object.fromEntries(FIELDS.map(key => [key, $(key).value]).concat([['headshot', $('headshot').checked]]));
const line = (label, value) => `<div class="resultLine"><span>${escape(label)}</span><strong>${escape(value)}</strong></div>`;
function impactHtml(result) {
  return line('Barrier absorbed', fmt(result.absorbed)) + line('Damage to health', fmt(result.healthDamage)) +
    line('Target health remaining', fmt(result.remaining)) +
    `<div class="hpTrack" aria-hidden="true"><span style="width:${Math.max(0, 100 - Math.min(100, result.percent))}%"></span></div>`;
}
function save() {
  try { localStorage.setItem(KEY, JSON.stringify({ fields: input(), items: [...selected], abilities: abilityInputs() })); } catch { /* Storage may be disabled. */ }
}
function abilityInputs() {
  return abilities.map((_, i) => ({ rank: $('rank' + i)?.value, property: $('property' + i)?.value,
    quantity: $('quantity' + i)?.value, type: $('type' + i)?.value }));
}

let previewStep = null;
function orderedItems() {
  const byId = new Map(shop.map(item => [item.id, item]));
  return [...selected].map(id => byId.get(id)).filter(Boolean);
}
function activeItems() {
  const items = orderedItems();
  return previewStep === null ? items : items.slice(0, previewStep);
}
function showBuildStep(step) {
  const count = selected.size;
  const value = Math.max(0, Math.min(count, Math.round(number(step))));
  previewStep = value === count ? null : value;
  render();
}
function renderBuildTimeline() {
  const items = orderedItems();
  const count = previewStep === null ? items.length : previewStep;
  const previewing = previewStep !== null;
  $('buildStep').max = items.length;
  $('buildStep').value = count;
  $('buildStep').disabled = !items.length;
  const label = previewing ? `Previewing step ${count} of ${items.length}` : `Full build · ${items.length} items`;
  $('buildStepLabel').textContent = label;
  $('buildStep').setAttribute('aria-valuetext', label);
  $('previousBuildStep').disabled = count === 0;
  $('nextBuildStep').disabled = count === items.length;
  $('returnFullBuild').hidden = !previewing;
  $('buildPreviewBanner').hidden = !previewing;
  $('buildPreviewText').textContent = count === 0 ? 'Preview: before your first item.' :
    `Preview: step ${count} of ${items.length} — after ${items[count - 1]?.name}.`;
  let spent = 0;
  $('equipped').innerHTML = items.map((item, index) => {
    spent += number(item.cost);
    const step = index + 1;
    return `<div class="buildItem ${step > count ? 'futureBuildItem' : ''}" data-build-item="${item.id}">
      <button class="buildItemStep" type="button" data-build-step="${step}" aria-label="Preview step ${step}: ${escape(item.name)}" aria-pressed="${previewing && count === step}">
        <span class="buildItemNumber">${step}</span><span class="buildItemName">${escape(item.name)}<small>${fmt(spent)} souls total${step > count ? ' · Later item' : ''}</small></span>
      </button><div class="buildItemActions">
        <button type="button" data-move-item="${item.id}" data-direction="-1" aria-label="Move ${escape(item.name)} earlier" ${index === 0 ? 'disabled' : ''}>↑</button>
        <button type="button" data-move-item="${item.id}" data-direction="1" aria-label="Move ${escape(item.name)} later" ${index === items.length - 1 ? 'disabled' : ''}>↓</button>
        <button type="button" data-remove="${item.id}" aria-label="Remove ${escape(item.name)}">×</button>
      </div></div>`;
  }).join('') || '<p class="subtle">Add items to start a build order.</p>';
}

function itemPicker() {
  const query = $('itemSearch').value.trim().toLowerCase();
  const matches = shop.filter(item => item.name.toLowerCase().includes(query));
  $('itemPicker').innerHTML = matches.map(item => `<button type="button" data-add="${item.id}" ${selected.has(item.id) ? 'disabled' : ''}><span>${escape(item.name)}</span><small>${fmt(item.cost)} · ${escape(item.item_slot_type)}</small></button>`).join('') || '<p class="subtle">No matching items.</p>';
  $('itemCount').textContent = '(' + selected.size + ')';
  renderBuildTimeline();
}
function setHero(restored = null) {
  hero = data.heroes.find(row => String(row.id) === $('hero').value);
  const byClass = new Map(data.items.map(item => [item.class_name, item]));
  abilities = [1, 2, 3, 4].map(n => byClass.get(hero.items?.['signature' + n]) || { name: 'Ability ' + n, properties: {} });
  $('boons').max = progression(hero, Infinity).max;
  $('boons').value = Math.min(number($('boons').value), Number($('boons').max));
  // The final headshot multiplier is an explicit scenario input, not inferred from a bonus field.
  $('abilities').innerHTML = abilities.map((ability, i) => {
    const props = damageProperties(ability);
    return `<article class="abilityCard"><h3>${i + 1}. ${escape(ability.name)}</h3><div class="abilityControls">
      <label>Ability upgrades<select id="rank${i}"><option value="-1">Locked</option>${AP_COSTS.map((cost, rank) => `<option value="${rank}">${cost} AP · ${rank === 0 ? 'Base' : 'Tier ' + rank}</option>`).join('')}</select></label>
      <label>Damage component<select id="property${i}">${props.map(([key, prop]) => `<option value="${escape(key)}">${escape(prop.label || key)} · ${escape(key)}</option>`).join('') || '<option value="">No direct component</option>'}</select></label>
      <label><span id="quantityLabel${i}">Hits / ticks</span><input id="quantity${i}" type="number" min="0" max="1000" step="1" value="1" required></label>
      <label>Damage type<select id="type${i}"><option value="">Select type</option><option value="spirit">Spirit</option><option value="bullet">Bullet</option></select></label>
      </div><div id="abilityResult${i}" aria-live="polite"></div>
      <details><summary>Upgrade details and conditions</summary><p class="formula">${escape(Object.values(ability.description || {}).filter(x => typeof x === 'string').join(' '))}</p>
      ${(ability.upgrades || []).map((tier, rank) => `<p class="formula">Tier ${rank + 1}: ${escape((tier.property_upgrades || []).map(p => (ability.properties?.[p.name]?.label || p.name) + ' ' + p.bonus + (p.upgrade_type ? ' (' + p.upgrade_type + ')' : '')).join('; '))}</p>`).join('')}
      ${ability.dependent_abilities ? '<p class="notice">Linked ability effects require separate formulas and are not included in this component.</p>' : ''}</details></article>`;
  }).join('');
  abilities.forEach((ability, i) => {
    $('rank' + i).value = i === 0 ? '0' : '-1';
    const saved = restored?.[i];
    if (saved) for (const field of ['rank','property','quantity','type']) if (saved[field] !== undefined) $(field + i).value = saved[field];
    updateComponent(i, !saved);
  });
}
function updateComponent(i, resetType) {
  const prop = abilities[i].properties?.[$('property' + i).value];
  const perSecond = /DPS|DamagePerSecond/i.test($('property' + i).value) || /per second/i.test(prop?.label || '');
  $('quantityLabel' + i).textContent = perSecond ? 'Exposure (seconds)' : 'Hits / ticks';
  $('quantity' + i).step = perSecond ? '0.1' : '1';
  if (resetType) $('type' + i).value = prop?.css_class === 'tech_damage' ? 'spirit' : prop?.css_class === 'bullet_damage' ? 'bullet' : '';
}
function render() {
  renderBuildTimeline();
  if (!$('calculatorForm').checkValidity()) {
    $('status').textContent = 'Correct the highlighted fields to calculate. Previous results are hidden.';
    $('bulletResults').replaceChildren();
    $('buildSummary').replaceChildren();
    $('attackerStats').replaceChildren();
    abilities.forEach((_, i) => $('abilityResult' + i).replaceChildren());
    return;
  }
  const values = input();
  const stats = buildStats(hero, activeItems(), values);
  $('status').textContent = `Cached assets: ${data.generatedAt ? new Date(data.generatedAt).toLocaleString() : 'date unavailable'} · Results depend on this snapshot and the conditions entered below.`;
  $('progression').textContent = `${fmt(stats.level.souls)} souls · ${stats.level.ap} AP available · ${stats.level.unlocks} ability unlocks`;
  const weapon = data.items.find(item => item.class_name === hero.items?.weapon_primary);
  const gun = weaponStats(hero, weapon, stats);
  $('attackerStats').innerHTML = line('Maximum health', fmt(Math.ceil(stats.health))) +
    line('Light melee damage', fmt(stats.lightMelee)) + line('Heavy melee damage', fmt(stats.heavyMelee)) +
    line('Total ammo (magazine)', fmt(gun.ammo)) +
    line('Fire rate (shots/sec)', fmt(gun.rate)) +
    line('Fire rate bonus', fmt(gun.fireRatePercent) + '%') +
    `<p class="formula">Health: (${fmt(stats.healthBase)} base × ${fmt(1 + (stats.shopHealth + stats.healthBasePercent) / 100)} + ${fmt(stats.healthFlat)} flat) × ${fmt(1 + stats.healthPercent / 100)}. Melee bonus: ${fmt(stats.weaponPercent / 2)}% from weapon damage + ${fmt(stats.meleePercent)}% melee.</p>`;
  const totalCost = Object.values(stats.spent).reduce((a, b) => a + b, 0);
  $('buildSummary').innerHTML = [['Spirit power', fmt(stats.spirit)], ['Weapon bonus', fmt(stats.weaponPercent) + '%'], ['Build cost', fmt(totalCost)]].map(([label, value]) => `<div class="statBox"><small>${label}</small><strong>${value}</strong></div>`).join('');
  const bullet = weaponDamage(hero, weapon, stats, values);
  $('bulletResults').innerHTML = bullet.error ? `<p class="notice">${escape(bullet.error)}</p>` :
    line('Body damage / bullet', fmt(bullet.body)) + line('Head damage / bullet', fmt(bullet.head)) +
    line(`Damage / shot (${bullet.pellets} pellets)`, fmt(bullet.shot)) + line('DPS while firing', fmt(bullet.dps)) +
    impactHtml(bullet.impact) + `<p class="formula">(${fmt(bullet.base)} base × ${fmt(1 + stats.weaponPercent / 100)} weapon multiplier + ${fmt(number(values.flatBullet))} flat) × ${fmt(number(values.falloff) / 100)} falloff × ${fmt(1 - (number(values.bulletResist) - number(values.bulletShred)) / 100)} resistance × ${fmt(1 + number(values.bulletAmp) / 100)} amplification. Headshot multiplier: ${fmt(bullet.headMultiplier)}.</p>`;
  let spentAp = 0, unlocked = 0;
  abilities.forEach((ability, i) => {
    const rank = Number($('rank' + i).value);
    spentAp += rank >= 0 ? AP_COSTS[rank] : 0;
    unlocked += rank >= 0 ? 1 : 0;
    const container = $('abilityResult' + i);
    if (rank < 0) { container.innerHTML = '<p class="subtle">Ability locked.</p>'; return; }
    const key = $('property' + i).value, type = $('type' + i).value;
    if (!key) { container.innerHTML = '<p class="notice">No supported direct damage component. This ability may deal damage through a buff, linked effect, or special formula.</p>'; return; }
    if (!type) { container.innerHTML = '<p class="notice">Select the damage type for this component.</p>'; return; }
    const component = propertyValue(ability, key, rank, stats);
    if (component.value === null) { container.innerHTML = `<p class="notice">${escape(component.reason)}. No damage result.</p>`; return; }
    const quantity = number($('quantity' + i).value);
    const raw = component.value * quantity;
    const resistance = number(values[type + 'Resist']) - number(values[type + 'Shred']);
    const dealt = damageTaken(raw, resistance, values[type + 'Amp']);
    container.innerHTML = line('Raw component damage', fmt(raw)) + line('Damage after defenses', fmt(dealt)) +
      impactHtml(impact(dealt, number(values.health), number(values.barrier))) +
      `<p class="formula">(${fmt(component.base)} upgraded base + ${fmt(stats.spirit)} spirit × ${fmt(component.scale)}) × ${fmt(quantity)} ${$('quantityLabel' + i).textContent.toLowerCase()} × ${fmt(1 - resistance / 100)} resistance × ${fmt(1 + number(values[type + 'Amp']) / 100)} amplification.</p>`;
  });
  const illegal = spentAp > stats.level.ap || unlocked > stats.level.unlocks || (Number($('rank3').value) >= 0 && stats.level.unlocks < 4);
  $('apBudget').textContent = `${spentAp} / ${stats.level.ap} AP${illegal ? ' · Sandbox allocation exceeds unlocks or AP' : ''}`;
  $('apBudget').className = illegal ? 'notice' : 'subtle';
  $('coverage').innerHTML = `<p class="formula">Shop investment: +${fmt(stats.shopSpirit)} spirit and +${fmt(stats.shopWeapon)}% weapon damage, +${fmt(stats.shopHealth)}% base health.</p>` +
    stats.applied.map(item => `<p class="formula">${escape(item.name)}: ${escape(item.bonuses.join(', ') || 'shop investment only')}</p>`).join('') +
    (stats.omitted.length ? `<details open><summary>${stats.omitted.length} item properties not automatically applied</summary><ul>${stats.omitted.map(note => `<li class="formula">${escape(note)}</li>`).join('')}</ul><p class="notice">Enter applicable bonuses in the extra stats, amplification, resist reduction, or spirit override fields. Procs are not included in the displayed hits.</p></details>` : '');
  save();
}
async function init() {
  try {
    const response = await fetch('/api/damage-data');
    if (!response.ok) throw new Error(`Asset request failed (${response.status})`);
    data = await response.json();
    if (!data.heroes?.length || !data.items?.length) throw new Error('No cached hero or item assets. Build the asset manifest and restart the UI server.');
    data.heroes.sort((a, b) => a.name.localeCompare(b.name));
    shop = data.items.filter(item => item.type === 'upgrade' && item.shopable && item.cost > 0).sort((a, b) => a.name.localeCompare(b.name));
    $('hero').innerHTML = data.heroes.map(row => `<option value="${row.id}">${escape(row.name)}</option>`).join('');
    $('hero').value = String(data.heroes.find(row => row.name === 'Infernus')?.id || data.heroes[0].id);
    let restored;
    try { restored = JSON.parse(localStorage.getItem(KEY)); } catch { /* Invalid saved state is discarded. */ }
    if (restored?.fields && typeof restored.fields === 'object') {
      for (const field of FIELDS) if (restored.fields[field] !== undefined && (field !== 'hero' || data.heroes.some(h => String(h.id) === String(restored.fields.hero)))) $(field).value = restored.fields[field];
      $('headshot').checked = restored.fields.headshot === true;
      selected = new Set((Array.isArray(restored.items) ? restored.items : []).filter(id => shop.some(item => item.id === id)));
    }
    setHero(Array.isArray(restored?.abilities) ? restored.abilities : null);
    itemPicker();
    $('calculatorForm').hidden = false;
    render();
  } catch (error) {
    $('status').textContent = error.message + ' Reload this page to retry.';
    $('status').className = 'notice';
  }
}
$('calculatorForm').addEventListener('submit', event => event.preventDefault());
$('calculatorForm').addEventListener('input', event => {
  if (event.target.id === 'buildStep') return;
  if (event.target.id === 'itemSearch') { itemPicker(); return; }
  if (event.target.id === 'hero') setHero();
  const match = event.target.id.match(/^property(\d)$/);
  if (match) updateComponent(Number(match[1]), true);
  render();
});
$('itemPicker').addEventListener('click', event => {
  const button = event.target.closest('[data-add]');
  if (button) { previewStep = null; selected.add(Number(button.dataset.add)); itemPicker(); render(); }
});
$('equipped').addEventListener('click', event => {
  const stepButton = event.target.closest('[data-build-step]');
  if (stepButton) {
    const step = Number(stepButton.dataset.buildStep);
    showBuildStep(step);
    $('equipped').querySelector(`[data-build-step="${step}"]`)?.focus({ preventScroll: true });
    return;
  }
  const move = event.target.closest('[data-move-item]');
  if (move) {
    const order = [...selected], id = Number(move.dataset.moveItem);
    const index = order.indexOf(id), destination = index + Number(move.dataset.direction);
    if (index < 0 || destination < 0 || destination >= order.length) return;
    [order[index], order[destination]] = [order[destination], order[index]];
    selected = new Set(order);
    previewStep = null;
    itemPicker(); render();
    $('equipped').querySelector(`[data-build-item="${id}"] .buildItemStep`)?.focus({ preventScroll: true });
    return;
  }
  const button = event.target.closest('[data-remove]');
  if (button) { previewStep = null; selected.delete(Number(button.dataset.remove)); itemPicker(); render(); }
});
$('clearItems').addEventListener('click', () => { previewStep = null; selected.clear(); itemPicker(); render(); });
$('resetCalculator').addEventListener('click', () => {
  $('calculatorForm').reset(); previewStep = null; selected.clear(); $('hero').value = String(data.heroes.find(row => row.name === 'Infernus')?.id || data.heroes[0].id);
  setHero(); itemPicker(); render();
});

let inventoryType = '';
const inventoryTypeNames = { weapon: 'Weapon', vitality: 'Vitality', spirit: 'Spirit' };
function renderInventory() {
  const query = $('inventorySearch').value.trim().toLowerCase();
  const tier = $('inventoryTier').value;
  const matches = shop.filter(item => (!inventoryType || item.item_slot_type === inventoryType) &&
    (!tier || String(item.item_tier) === tier) && item.name.toLowerCase().includes(query));
  $('inventoryCount').textContent = matches.length + ' matching items';
  const equippedItems = orderedItems();
  $('inventorySummary').textContent = equippedItems.length + ' equipped · ' +
    fmt(equippedItems.reduce((sum, item) => sum + number(item.cost), 0)) + ' souls' +
    (previewStep === null ? '' : ' · Previewing step ' + previewStep + '; edits return to full build');
  $('inventoryResults').innerHTML = Object.entries(inventoryTypeNames).map(([type, name]) => {
    const items = matches.filter(item => item.item_slot_type === type);
    if (!items.length) return '';
    const tiers = [...new Set(items.map(item => number(item.item_tier)))].sort((a, b) => a - b);
    return `<section class="inventoryCategory" data-category="${type}"><h3>${name} <small>${items.length}</small></h3>${tiers.map(tier => {
      const tierItems = items.filter(item => number(item.item_tier) === tier);
      const costs = [...new Set(tierItems.map(item => number(item.cost)))].sort((a, b) => a - b);
      return costs.map(cost => `<section class="inventoryTierGroup"><h4>Tier ${tier} <span>${fmt(cost)} souls</span></h4><div class="inventoryCards">${tierItems.filter(item => number(item.cost) === cost).map(item => {
        const equipped = selected.has(item.id);
        return `<button type="button" class="inventoryCard" data-inventory-item="${item.id}" aria-pressed="${equipped}" aria-label="${equipped ? 'Remove' : 'Equip'} ${escape(item.name)}"><span>${escape(item.name)}</span><small>${equipped ? '✓ Equipped · Step ' + ([...selected].indexOf(item.id) + 1) : '+ Equip'}</small></button>`;
      }).join('')}</div></section>`).join('');
    }).join('')}</section>`;
  }).join('') || '<p class="inventoryEmpty">No items match these filters. Try another type, tier, or search.</p>';
  $('inventoryResults').classList.toggle('singleCategory', Boolean(inventoryType));
}
$('browseInventory').addEventListener('click', () => {
  const previousTier = $('inventoryTier').value;
  const tiers = [...new Set(shop.map(item => number(item.item_tier)))].sort((a, b) => a - b);
  $('inventoryTier').innerHTML = '<option value="">All tiers / costs</option>' + tiers.map(tier => {
    const costs = [...new Set(shop.filter(item => number(item.item_tier) === tier).map(item => number(item.cost)))].sort((a, b) => a - b);
    return `<option value="${tier}">Tier ${tier} · ${costs.map(fmt).join(' / ')} souls</option>`;
  }).join('');
  $('inventoryTier').value = previousTier;
  renderInventory();
  $('inventoryModal').showModal();
  document.body.classList.add('inventoryOpen');
  $('inventorySearch').focus();
});
for (const id of ['closeInventory', 'doneInventory']) $(id).addEventListener('click', () => $('inventoryModal').close());
$('inventoryModal').addEventListener('close', () => document.body.classList.remove('inventoryOpen'));
$('inventoryModal').addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    event.preventDefault();
    $('inventoryModal').close();
  }
});
$('inventoryModal').addEventListener('click', event => {
  if (event.target !== $('inventoryModal')) return;
  const bounds = $('inventoryModal').getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) $('inventoryModal').close();
});
$('inventorySearch').addEventListener('input', renderInventory);
$('inventoryTier').addEventListener('change', renderInventory);
document.querySelector('.inventoryTypes').addEventListener('click', event => {
  const button = event.target.closest('[data-inventory-type]');
  if (!button) return;
  inventoryType = button.dataset.inventoryType;
  document.querySelectorAll('[data-inventory-type]').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
  renderInventory();
});
$('inventoryResults').addEventListener('click', event => {
  const button = event.target.closest('[data-inventory-item]');
  if (!button) return;
  const id = Number(button.dataset.inventoryItem);
  previewStep = null;
  if (selected.has(id)) selected.delete(id);
  else selected.add(id);
  itemPicker();
  render();
  renderInventory();
  $('inventoryResults').querySelector(`[data-inventory-item="${id}"]`)?.focus({ preventScroll: true });
});


$('buildStep').addEventListener('input', () => showBuildStep($('buildStep').value));
$('previousBuildStep').addEventListener('click', () => showBuildStep((previewStep ?? selected.size) - 1));
$('nextBuildStep').addEventListener('click', () => showBuildStep((previewStep ?? selected.size) + 1));
for (const id of ['returnFullBuild', 'exitBuildPreview']) $(id).addEventListener('click', () => showBuildStep(selected.size));

init();
