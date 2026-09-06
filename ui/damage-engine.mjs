// Pure calculations shared by the page and regression tests.
export const AP_COSTS = [0, 1, 3, 8];
export const number = (value, fallback = 0) => {
  if (value === null || value === undefined || value === '') return fallback;
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
};
export const clamp = (value, min, max) => Math.min(max, Math.max(min, number(value, min)));
export function numeric(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string' || !/^[+-]?(?:\d+\.?\d*|\.\d+)\s*(?:%|m|s)?$/.test(value.trim())) return null;
  return Number.parseFloat(value);
}
const stat = (hero, key, fallback = 0) => number(hero.starting_stats?.[key]?.value, fallback);
export function progression(hero, boons) {
  const levels = Object.entries(hero.level_info || {}).sort((a, b) => Number(a[0]) - Number(b[0]));
  const max = levels.filter(([, row]) => row.use_standard_upgrade).length;
  const count = Math.round(clamp(boons, 0, max));
  let seen = 0, ap = 0, unlocks = 0, souls = 0;
  for (const [, row] of levels) {
    if (row.use_standard_upgrade && seen === count) break;
    if (row.use_standard_upgrade) seen++;
    souls = number(row.required_gold);
    ap += (row.bonus_currencies || []).filter(x => x === 'EAbilityPoints').length;
    unlocks += (row.bonus_currencies || []).filter(x => x === 'EAbilityUnlocks').length;
  }
  return { count, max, ap, unlocks, souls };
}
export function investmentBonus(hero, category, spent) {
  return (hero.cost_bonuses?.[category] || []).filter(row => row.gold_threshold <= spent)
    .sort((a, b) => b.gold_threshold - a.gold_threshold)[0]?.bonus || 0;
}
const MODIFIERS = {
  MODIFIER_VALUE_TECH_POWER: 'spirit',
  MODIFIER_VALUE_TECH_POWER_PERCENT: 'spiritPercent',
  MODIFIER_VALUE_WEAPON_POWER: 'weaponPercent',
  MODIFIER_VALUE_WEAPON_DAMAGE_INCREASE: 'weaponPercent',
  MODIFIER_VALUE_FIRE_RATE: 'fireRate',
  MODIFIER_VALUE_AMMO_CLIP_SIZE: 'ammoFlat',
  MODIFIER_VALUE_AMMO_CLIP_SIZE_PERCENT: 'ammoPercent',
  MODIFIER_VALUE_HEALTH_MAX: 'healthFlat',
  MODIFIER_VALUE_BASE_HEALTH_PERCENT: 'healthBasePercent',
  MODIFIER_VALUE_HEALTH_MAX_PERCENT: 'healthPercent',
  MODIFIER_VALUE_MELEE_DAMAGE_INCREASE: 'meleePercent',
};
export function buildStats(hero, items, input = {}) {
  const level = progression(hero, input.boons);
  const upgrades = hero.standard_level_up_upgrades || {};
  const stats = { spirit: stat(hero, 'tech_power') + level.count * number(upgrades.MODIFIER_VALUE_TECH_POWER),
    spiritPercent: 0, weaponPercent: stat(hero, 'weapon_power'), fireRate: 0, ammoFlat: 0, ammoPercent: 0,
    healthFlat: 0, healthBasePercent: 0, healthPercent: 0, meleePercent: 0 };
  const spent = { weapon: 0, spirit: 0, vitality: 0 }, applied = [], omitted = [];
  for (const item of [...new Map(items.map(item => [item.id, item])).values()]) {
    if (item.item_slot_type in spent) spent[item.item_slot_type] += number(item.cost);
    const bonuses = [];
    for (const [key, prop] of Object.entries(item.properties || {})) {
      const value = numeric(prop.value);
      if (value === null || value === 0) continue;
      const conditional = prop.conditional || prop.usage_flags?.includes('ConditionallyApplied') ||
        ['active', 'passive'].includes(prop.tooltip_section);
      const field = MODIFIERS[prop.provided_property_type];
      if (field && !conditional && !prop.scale_function) {
        stats[field] += value;
        bonuses.push(`${prop.label || key}: +${value}${prop.postfix || ''}`);
      } else if (field || /damage|power|health|melee|ammo|clip|fire.?rate|resist|duration|reload|imbu|range/i.test(key)) {
        omitted.push(`${item.name}: ${prop.label || key} (${value}${prop.postfix || ''})`);
      }
    }
    applied.push({ name: item.name, bonuses });
  }
  // Investment thresholds replace legacy per-tier purchase bonuses.
  const shopSpirit = investmentBonus(hero, 'spirit', spent.spirit);
  const shopWeapon = investmentBonus(hero, 'weapon', spent.weapon);
  stats.spirit = (stats.spirit + shopSpirit + number(input.extraSpirit)) * (1 + stats.spiritPercent / 100);
  stats.weaponPercent += shopWeapon + number(input.extraWeapon);
  if (input.spiritOverride !== '' && input.spiritOverride !== undefined) stats.spirit = Math.max(0, number(input.spiritOverride));
  const shopHealth = investmentBonus(hero, 'vitality', spent.vitality);
  const healthBase = stat(hero, 'max_health') + level.count * number(upgrades.MODIFIER_VALUE_BASE_HEALTH_FROM_LEVEL);
  const health = Math.max(0, (healthBase * (1 + (shopHealth + stats.healthBasePercent) / 100) + stats.healthFlat)
    * (1 + stats.healthPercent / 100));
  const lightBase = stat(hero, 'light_melee_damage');
  const heavyBase = stat(hero, 'heavy_melee_damage');
  const meleeGrowth = level.count * number(upgrades.MODIFIER_VALUE_BASE_MELEE_DAMAGE_FROM_LEVEL);
  const meleeMultiplier = Math.max(0, 1 + stats.weaponPercent / 200 + stats.meleePercent / 100);
  function meleeValue(base, growth, key) {
    const scaling = hero.scaling_stats?.[key];
    if (scaling && scaling.scaling_stat !== 'ETechPower') return null;
    return Math.max(0, (base + growth + number(scaling?.scale) * stats.spirit) * meleeMultiplier);
  }
  const lightMelee = meleeValue(lightBase, meleeGrowth, 'ELightMeleeDamage');
  const heavyMelee = lightBase > 0 ? meleeValue(heavyBase, meleeGrowth * heavyBase / lightBase, 'EHeavyMeleeDamage') : null;
  return { ...stats, level, spent, shopSpirit, shopWeapon, shopHealth, healthBase, health,
    lightMelee, heavyMelee, meleeMultiplier, applied, omitted };
}
export function propertyValue(asset, key, rank, context) {
  const prop = asset.properties?.[key];
  let base = numeric(prop?.value);
  if (base === null) return { value: null, reason: 'No numeric base value' };
  let scale = number(prop.scale_function?.stat_scale);
  for (const tier of (asset.upgrades || []).slice(0, clamp(rank, 0, 3))) {
    for (const change of tier.property_upgrades || []) {
      if (change.name !== key) continue;
      const bonus = numeric(change.bonus);
      if (bonus === null) return { value: null, reason: 'Unsupported upgrade value' };
      switch (change.upgrade_type || 'EAddToBase') {
        case 'EAddToBase': base += bonus; break;
        case 'EMultiplyBase': base *= bonus; break;
        case 'EAddToScale': scale += bonus; break;
        case 'EMultiplyScale': scale *= bonus; break;
        default: return { value: null, reason: `Unsupported upgrade: ${change.upgrade_type}` };
      }
    }
  }
  const fn = prop.scale_function;
  let scaling = 0;
  if (fn) {
    if (fn.class_name === 'scale_function_tech_damage') scaling = context.spirit * scale;
    else return { value: null, reason: `Requires special scaling: ${fn.class_name}` };
  }
  return { value: Math.max(0, base + scaling), base, scale, scaling };
}
export function damageTaken(raw, resistance, amplification = 0) {
  return Math.max(0, raw) * (1 - clamp(resistance, -200, 100) / 100) * (1 + clamp(amplification, -100, 1000) / 100);
}
export function impact(damage, health, barrier = 0) {
  const absorbed = Math.min(Math.max(0, barrier), damage);
  const healthDamage = Math.max(0, damage - absorbed);
  return { absorbed, healthDamage, remaining: Math.max(0, health - healthDamage), percent: health > 0 ? healthDamage / health * 100 : 0 };
}
export function weaponStats(hero, weapon, stats) {
  const info = weapon?.weapon_info || {};
  const spiritBonus = key => {
    const scaling = hero.scaling_stats?.[key];
    if (!scaling) return 0;
    return scaling.scaling_stat === 'ETechPower' ? number(scaling.scale) * stats.spirit : null;
  };
  const ammoScaling = spiritBonus('EClipSize');
  const baseAmmo = numeric(info.clip_size);
  const ammo = baseAmmo === null || ammoScaling === null ? null :
    Math.max(0, Math.ceil((baseAmmo + ammoScaling + number(stats.ammoFlat)) * (1 + number(stats.ammoPercent) / 100) - 1e-9));
  // EFireRate and ERoundsPerSecond can describe the same scaling. Apply only one.
  const fireScaling = spiritBonus('EFireRate');
  const flatRateScaling = hero.scaling_stats?.EFireRate ? 0 : spiritBonus('ERoundsPerSecond');
  const fireRatePercent = fireScaling === null ? null : number(stats.fireRate) + fireScaling;
  const baseRate = numeric(info.shots_per_second);
  const modifier = Math.max(-0.5, number(fireRatePercent) / 100);
  const rate = baseRate === null || fireRatePercent === null || flatRateScaling === null ? null :
    Math.max(0, (baseRate + flatRateScaling) * (modifier >= 0 ? 1 + modifier : 1 / (1 - modifier)));
  return { ammo, baseAmmo, ammoScaling, fireRatePercent, rate };
}
export function weaponDamage(hero, weapon, stats, input) {
  const info = weapon?.weapon_info;
  if (!info || numeric(info.bullet_damage) === null) return { error: 'No primary weapon damage in this snapshot.' };
  const levelScale = number(hero.standard_level_up_upgrades?.MODIFIER_VALUE_BASE_BULLET_DAMAGE_FROM_LEVEL);
  const spiritScale = hero.scaling_stats?.EBulletDamage;
  if (spiritScale && spiritScale.scaling_stat !== 'ETechPower') return { error: 'This weapon needs a special scaling formula.' };
  const base = info.bullet_damage * (1 + stats.level.count * levelScale) + number(spiritScale?.scale) * stats.spirit;
  const raw = Math.max(0, base * (1 + stats.weaponPercent / 100) + number(input.flatBullet));
  const falloff = clamp(input.falloff ?? 100, 0, 100) / 100;
  const headMultiplier = clamp(input.headMultiplier ?? info.crit_bonus_start ?? 1, 1, 10);
  const resist = number(input.bulletResist) - number(input.bulletShred);
  const body = damageTaken(raw * falloff, resist, input.bulletAmp);
  const head = body * headMultiplier;
  const pellets = Math.max(1, number(info.bullets, 1));
  const shot = (input.headshot ? head : body) * pellets;
  const { rate } = weaponStats(hero, weapon, stats);
  return { base, raw, body, head, pellets, shot, rate, dps: rate === null ? null : shot * rate,
    impact: impact(shot, input.health, input.barrier), headMultiplier };
}
export function damageProperties(asset) {
  // Percentages, multipliers and damage thresholds are not standalone hits.
  return Object.entries(asset.properties || {}).filter(([key, prop]) => {
    const label = `${key} ${prop.label || ''}`;
    return /damage|dps/i.test(label) && !/percent|scale|minimum|threshold|reduction|resist|amplif|incoming|outgoing|weaponpower|WeaponDamageBonus|BonusWeaponDamage|lifesteal|heal/i.test(key)
      && prop.postfix !== '%' && !String(prop.value).includes('%')
      && (prop.css_class === 'tech_damage' || prop.css_class === 'bullet_damage' || /^(Damage|DPS|DamagePerSecond|ImpactDamage|ExplosionDamage|TickDamage|DamagePerTick|BurnDamage|BonusDamage)$/.test(key));
  });
}
