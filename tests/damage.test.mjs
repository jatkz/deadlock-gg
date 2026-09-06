import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { progression, buildStats, propertyValue, weaponStats, weaponDamage, damageTaken, impact, investmentBonus, damageProperties, numeric } from '../ui/damage-engine.mjs';
const manifest = JSON.parse(readFileSync(new URL('../assets/deadlock/manifest.json', import.meta.url), 'utf8'));
const heroes = manifest.raw.heroes;
const byClass = new Map(manifest.raw.items.map(item => [item.class_name, item]));
const infernus = heroes.find(hero => hero.name === 'Infernus');
const approx = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-8, `${actual} != ${expected}`);
test('boon zero retains initial unlock but no standard upgrades', () => {
  const level = progression(infernus, 0);
  assert.equal(level.count, 0); assert.equal(level.ap, 0); assert.equal(level.unlocks, 1);
  assert.equal(progression(infernus, 1).ap, 1);
  assert.equal(progression(infernus, 2).unlocks, 2);
  assert.equal(progression(infernus, 9999).count, level.max);
});
test('investment selects one threshold and never adds legacy purchase bonuses', () => {
  const hero = { level_info: {}, purchase_bonuses: { spirit: [{ tier: 1, value: 999 }] },
    cost_bonuses: { spirit: [{ gold_threshold: 800, bonus: 7 }, { gold_threshold: 1600, bonus: 11 }] } };
  const item = { id: 1, cost: 800, item_slot_type: 'spirit', properties: { TechPower: { value: 10, provided_property_type: 'MODIFIER_VALUE_TECH_POWER' } } };
  assert.equal(investmentBonus(hero, 'spirit', 799), 0);
  assert.equal(buildStats(hero, [item]).spirit, 17);
  assert.equal(buildStats(hero, [item, item]).spirit, 17);
  assert.equal(buildStats(hero, [item, { ...item, id: 2 }]).spirit, 31);
});
test('conditional and active item stats are not silently counted', () => {
  const item = { id: 1, properties: { X: { value: 50, provided_property_type: 'MODIFIER_VALUE_TECH_POWER', usage_flags: ['ConditionallyApplied'] } } };
  const stats = buildStats({ level_info: {} }, [item]);
  assert.equal(stats.spirit, 0); assert.equal(stats.omitted.length, 1);
});
test('spirit percent applies after flat bonuses and override is final', () => {
  const item = { id: 1, properties: { X: { value: 25, provided_property_type: 'MODIFIER_VALUE_TECH_POWER_PERCENT' } } };
  assert.equal(buildStats({}, [item], { extraSpirit: 100 }).spirit, 125);
  assert.equal(buildStats({}, [item], { extraSpirit: 100, spiritOverride: '0' }).spirit, 0);
});
test('base and coefficient upgrades multiply rather than becoming additive', () => {
  const ability = { properties: { Damage: { value: 100, scale_function: { class_name: 'scale_function_tech_damage', stat_scale: 2 } } },
    upgrades: [{ property_upgrades: [{ name: 'Damage', bonus: 1.5, upgrade_type: 'EMultiplyBase' }, { name: 'Damage', bonus: 2, upgrade_type: 'EMultiplyScale' }] },
    { property_upgrades: [{ name: 'Damage', bonus: 10 }, { name: 'Damage', bonus: .5, upgrade_type: 'EAddToScale' }] }] };
  assert.equal(propertyValue(ability, 'Damage', 2, { spirit: 20 }).value, 250);
  assert.equal(propertyValue(ability, 'Damage', 0, { spirit: 20 }).value, 140);
});
test('unknown scaling and nonnumeric values produce no false result', () => {
  const asset = { properties: { Damage: { value: 50, scale_function: { class_name: 'special' } } } };
  assert.equal(propertyValue(asset, 'Damage', 0, {}).value, null);
  assert.equal(numeric('20 to 50'), null); assert.equal(numeric(''), null);
  assert.equal(numeric('15m'), 15);
});
test('positive, negative, and complete resistance plus amplification', () => {
  assert.equal(damageTaken(100, 25), 75);
  assert.equal(damageTaken(100, -25), 125);
  assert.equal(damageTaken(100, 100), 0);
  assert.equal(damageTaken(100, 25, 20), 90);
});
test('barriers absorb once and overkill never makes health negative', () => {
  assert.deepEqual(impact(80, 100, 100), { absorbed: 80, healthDamage: 0, remaining: 100, percent: 0 });
  assert.deepEqual(impact(250, 100, 50), { absorbed: 50, healthDamage: 200, remaining: 0, percent: 200 });
});
test('bullet boon growth, weapon bonus, falloff, pellets, and headshots', () => {
  const hero = { standard_level_up_upgrades: { MODIFIER_VALUE_BASE_BULLET_DAMAGE_FROM_LEVEL: .1 } };
  const weapon = { weapon_info: { bullet_damage: 10, bullets: 5, shots_per_second: 2 } };
  const stats = { level: { count: 10 }, spirit: 0, weaponPercent: 50, fireRate: 25 };
  const result = weaponDamage(hero, weapon, stats, { flatBullet: 10, falloff: 50, bulletResist: 30, bulletShred: 10, headMultiplier: 2, headshot: true, health: 1000 });
  approx(result.body, 16); approx(result.head, 32); approx(result.shot, 160); approx(result.dps, 400);
});
test('cached Infernus base damage and spirit coefficient', () => {
  const stats = buildStats(infernus, [], { boons: 0, extraSpirit: 100 });
  const ability = byClass.get(infernus.items.signature1);
  const prop = ability.properties.Damage;
  approx(propertyValue(ability, 'Damage', 0, stats).value, Number(prop.value) + 100 * prop.scale_function.stat_scale);
  const weapon = byClass.get(infernus.items.weapon_primary);
  approx(weaponDamage(infernus, weapon, buildStats(infernus, []), { health: 1000 }).body, weapon.weapon_info.bullet_damage);
});
test('damage components exclude damage amplification and thresholds', () => {
  const properties = { Damage: { value: 40, css_class: 'tech_damage' }, MinimumDamage: { value: 80 },
    IncomingDamagePercent: { value: 20, postfix: '%', css_class: 'tech_damage' }, DPS: { value: 30 } };
  assert.deepEqual(damageProperties({ properties }).map(([key]) => key), ['Damage', 'DPS']);
});
test('every cached hero remains finite or explicitly unsupported at max boons and AP', () => {
  for (const hero of heroes) {
    const stats = buildStats(hero, [], { boons: 9999, extraSpirit: 100 });
    const bullet = weaponDamage(hero, byClass.get(hero.items?.weapon_primary), stats, { health: 1000 });
    assert.ok(bullet.error || Number.isFinite(bullet.shot), hero.name);
    for (let slot = 1; slot <= 4; slot++) {
      const ability = byClass.get(hero.items?.['signature' + slot]);
      if (!ability) continue;
      for (const [key] of damageProperties(ability)) {
        const result = propertyValue(ability, key, 3, stats);
        assert.ok(result.value === null || Number.isFinite(result.value), hero.name + ': ' + key);
      }
    }
  }
});

test('attacker health and melee include boon growth and half weapon scaling', () => {
  const stats = buildStats(infernus, [], { boons: 10, extraWeapon: 40 });
  approx(stats.health, 1220);
  approx(stats.lightMelee, 78.96);
  approx(stats.heavyMelee, 183.1872);
});
test('health applies vitality to base before flat health and max-health modifiers', () => {
  const item = { id: 1, cost: 800, item_slot_type: 'vitality', properties: {
    Health: { value: 210, provided_property_type: 'MODIFIER_VALUE_HEALTH_MAX' },
    Base: { value: 25, provided_property_type: 'MODIFIER_VALUE_BASE_HEALTH_PERCENT' },
    Loss: { value: -13, provided_property_type: 'MODIFIER_VALUE_HEALTH_MAX_PERCENT' },
    Melee: { value: 12, provided_property_type: 'MODIFIER_VALUE_MELEE_DAMAGE_INCREASE' },
    ActiveMelee: { value: 30, provided_property_type: 'MODIFIER_VALUE_MELEE_DAMAGE_INCREASE', tooltip_section: 'active' },
  } };
  const stats = buildStats(infernus, [item], { extraWeapon: 40 });
  approx(stats.health, (830 * 1.34 + 210) * .87);
  approx(stats.lightMelee, 66);
  approx(stats.heavyMelee, 153.12);
  assert.equal(stats.shopHealth, 9);
  assert.ok(stats.omitted.some(note => note.includes('ActiveMelee')));
});
test('Paige heavy melee includes spirit scaling without increasing light melee', () => {
  const hero = heroes.find(hero => hero.name === 'Paige');
  const base = buildStats(hero, []);
  const powered = buildStats(hero, [], { extraSpirit: 100 });
  approx(powered.heavyMelee - base.heavyMelee, 30);
  approx(powered.lightMelee, base.lightMelee);
});

test('ammo combines flat and spirit bonuses before percentages and rounds up', () => {
  const hero = { scaling_stats: { EClipSize: { scaling_stat: 'ETechPower', scale: .5 } } };
  const stats = { spirit: 10, ammoFlat: 5, ammoPercent: 19, fireRate: 0 };
  const result = weaponStats(hero, { weapon_info: { clip_size: 20, shots_per_second: 2, bullets: 9 } }, stats);
  assert.equal(result.ammo, 36);
  assert.equal(result.rate, 2);
});
test('cached magazine and fire rate item bonuses reach weapon stats', () => {
  const items = manifest.raw.items.filter(item => ['Extended Magazine', 'Rapid Rounds'].includes(item.name) && item.shopable);
  const stats = buildStats(infernus, items);
  const weapon = byClass.get(infernus.items.weapon_primary);
  const result = weaponStats(infernus, weapon, stats);
  assert.equal(result.ammo, 36);
  approx(result.rate, weapon.weapon_info.shots_per_second * 1.09);
  const damage = weaponDamage(infernus, weapon, stats, { health: 1000 });
  approx(damage.dps, damage.shot * result.rate);
});
test('hero fire-rate scaling is applied once and missing weapon stats stay unavailable', () => {
  const hero = heroes.find(hero => hero.name === 'Warden');
  const weapon = byClass.get(hero.items.weapon_primary);
  const stats = buildStats(hero, [], { extraSpirit: 100 });
  const result = weaponStats(hero, weapon, stats);
  approx(result.rate, weapon.weapon_info.shots_per_second * 1.25);
  assert.equal(weaponStats({}, {}, stats).ammo, null);
  assert.equal(weaponStats({}, {}, stats).rate, null);
});
