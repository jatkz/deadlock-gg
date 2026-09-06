// Run with node tests/damage.browser.cjs [path-to-playwright] [base-url].
const assert = require('node:assert/strict');
const { chromium } = require(process.argv[2] || 'playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto((process.argv[3] || 'http://localhost:8766') + '/damage.html');
    await page.locator('#calculatorForm').waitFor({ state: 'visible' });
    assert.match(await page.locator('#status').innerText(), /Cached assets/);
    await page.locator('#browseInventory').click();
    assert.ok(await page.locator('#inventoryModal').isVisible());
    assert.equal(await page.locator('.inventoryCategory').count(), 3);
    assert.ok(await page.locator('#inventorySearch').evaluate(el => el === document.activeElement));
    await page.locator('[data-inventory-type="vitality"]').click();
    await page.locator('#inventoryTier').selectOption('1');
    assert.equal(await page.locator('.inventoryCategory').count(), 1);
    assert.equal(await page.locator('.inventoryCategory').getAttribute('data-category'), 'vitality');
    await page.locator('#inventorySearch').fill('Extra Health');
    const inventoryItem = page.locator('[data-inventory-item]');
    assert.equal(await inventoryItem.count(), 1);
    assert.match(await page.locator('.inventoryTierGroup h4').innerText(), /Tier 1[\s\S]*800 souls/);
    await inventoryItem.click();
    assert.equal(await inventoryItem.getAttribute('aria-pressed'), 'true');
    assert.match(await page.locator('#inventorySummary').innerText(), /1 equipped.*800 souls/);
    assert.equal(await page.locator('#itemCount').innerText(), '(1)');
    assert.match(await page.locator('#attackerStats').innerText(), /1,115/);
    assert.ok(await inventoryItem.evaluate(el => el === document.activeElement));
    await inventoryItem.click();
    assert.equal(await page.locator('#itemCount').innerText(), '(0)');
    await page.locator('#inventorySearch').fill('no-item-matches-this');
    assert.equal(await page.locator('[data-inventory-item]').count(), 0);
    assert.match(await page.locator('#inventoryResults').innerText(), /No items match/);
    await page.keyboard.press('Escape');
    assert.ok(!(await page.locator('#inventoryModal').isVisible()));
    assert.ok(await page.locator('#browseInventory').evaluate(el => el === document.activeElement));
    await page.locator('#browseInventory').click();
    await page.locator('[data-inventory-type=""]').click();
    await page.locator('#inventoryTier').selectOption('');
    await page.locator('#inventorySearch').fill('');
    await page.screenshot({ path: require('node:path').join(require('node:os').tmpdir(), 'deadlock-inventory-desktop.png') });
    await page.locator('#doneInventory').click();
    assert.ok(!(await page.locator('#inventoryModal').isVisible()));
    assert.match(await page.locator('#abilityResult0').innerText(), /40/);
    assert.match(await page.locator('#attackerStats').innerText(), /Maximum health[\s\S]*830[\s\S]*Light melee damage[\s\S]*50[\s\S]*Heavy melee damage[\s\S]*116/);

    assert.match(await page.locator('#attackerStats').innerText(), /Total ammo \(magazine\)[\s\S]*27[\s\S]*Fire rate \(shots\/sec\)[\s\S]*9.52/);
    for (const name of ['Extended Magazine', 'Rapid Rounds']) {
      await page.locator('#itemSearch').fill(name);
      await page.locator('[data-add]').click();
    }
    assert.match(await page.locator('#attackerStats').innerText(), /36[\s\S]*10.38/);
    await page.locator('[data-build-step="1"]').click();
    assert.match(await page.locator('#attackerStats').innerText(), /36[\s\S]*9.52/);
    await page.locator('#previousBuildStep').click();
    assert.match(await page.locator('#attackerStats').innerText(), /27[\s\S]*9.52/);
    await page.locator('#exitBuildPreview').click();
    assert.match(await page.locator('#attackerStats').innerText(), /36[\s\S]*10.38/);
    await page.locator('#clearItems').click();

    await page.locator('#boons').fill('10');
    assert.match(await page.locator('#attackerStats').innerText(), /1,220[\s\S]*65.8[\s\S]*152.66/);
    await page.locator('#boons').fill('0');
    await page.locator('#extraSpirit').fill('100');
    assert.match(await page.locator('#abilityResult0').innerText(), /100/);
    await page.locator('#spiritResist').fill('25');
    assert.match(await page.locator('#abilityResult0').innerText(), /75/);
    await page.locator('#barrier').fill('20');
    assert.match(await page.locator('#abilityResult0').innerText(), /55/);
    await page.locator('#itemSearch').fill('Extra Spirit');
    await page.locator('[data-add]').click();
    assert.equal(await page.locator('#itemCount').innerText(), '(1)');
    assert.match(await page.locator('#buildSummary').innerText(), /117/);
    await page.reload();
    await page.locator('#calculatorForm').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#extraSpirit').inputValue(), '100');
    assert.equal(await page.locator('#itemCount').innerText(), '(1)');

    // Build order is insertion order; previews only change active inventory.
    for (const name of ['Extra Health', 'Rapid Rounds']) {
      await page.locator('#itemSearch').fill(name);
      await page.locator('[data-add]').click();
    }
    const orderedNames = () => page.locator('.buildItemName').evaluateAll(nodes => nodes.map(node => node.firstChild.textContent));
    assert.deepEqual(await orderedNames(), ['Extra Spirit', 'Extra Health', 'Rapid Rounds']);
    const fullSummary = await page.locator('#buildSummary').innerText();
    const fullAttacker = await page.locator('#attackerStats').innerText();
    await page.locator('[data-build-step="1"]').click();
    assert.ok(await page.locator('#buildPreviewBanner').isVisible());
    assert.match(await page.locator('#buildSummary').innerText(), /117[\s\S]*800/);
    assert.equal(await page.locator('.futureBuildItem').count(), 2);
    assert.equal(await page.locator('#itemCount').innerText(), '(3)');
    await page.locator('#previousBuildStep').click();
    assert.match(await page.locator('#buildPreviewText').innerText(), /before your first item/);
    assert.equal(await page.locator('.futureBuildItem').count(), 3);
    await page.locator('#nextBuildStep').click();
    assert.equal(await page.locator('#buildStep').inputValue(), '1');
    await page.locator('#exitBuildPreview').click();
    assert.equal(await page.locator('#buildSummary').innerText(), fullSummary);
    assert.equal(await page.locator('#attackerStats').innerText(), fullAttacker);
    await page.locator('#buildStep').fill('2');
    assert.equal(await page.locator('.futureBuildItem').count(), 1);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await page.locator('#equipped').screenshot({ path: require('node:path').join(require('node:os').tmpdir(), 'deadlock-build-order.png') });
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.reload();
    await page.locator('#calculatorForm').waitFor({ state: 'visible' });
    assert.deepEqual(await orderedNames(), ['Extra Spirit', 'Extra Health', 'Rapid Rounds']);
    assert.equal(await page.locator('#buildSummary').innerText(), fullSummary);
    assert.ok(!(await page.locator('#buildPreviewBanner').isVisible()));
    await page.getByRole('button', { name: 'Move Rapid Rounds earlier', exact: true }).click();
    assert.deepEqual(await orderedNames(), ['Extra Spirit', 'Rapid Rounds', 'Extra Health']);
    await page.locator('[data-build-step="1"]').click();
    await page.locator('#browseInventory').click();
    await page.locator('#inventorySearch').fill('Extra Health');
    assert.match(await page.locator('[data-inventory-item]').innerText(), /Step 3/);
    await page.locator('[data-inventory-item]').click();
    await page.locator('#doneInventory').click();
    assert.ok(!(await page.locator('#buildPreviewBanner').isVisible()));
    assert.equal(await page.locator('#buildStep').inputValue(), '2');
    await page.locator('[data-build-step="1"]').click();
    await page.getByRole('button', { name: 'Remove Rapid Rounds', exact: true }).click();
    assert.ok(!(await page.locator('#buildPreviewBanner').isVisible()));
    assert.deepEqual(await orderedNames(), ['Extra Spirit']);

    await page.locator('#rank0').selectOption('3');
    assert.match(await page.locator('#apBudget').innerText(), /Sandbox/);
    await page.locator('#boons').fill('35');
    assert.doesNotMatch(await page.locator('#apBudget').innerText(), /Sandbox/);
    await page.locator('#health').fill('');
    assert.equal(await page.locator('#bulletResults').innerText(), '');
    await page.locator('#health').fill('1000');
    assert.match(await page.locator('#bulletResults').innerText(), /DPS/);
    const heroIds = await page.locator('#hero option').evaluateAll(options => options.map(option => option.value));
    for (const id of heroIds) {
      await page.locator('#hero').selectOption(id);
      assert.equal(await page.locator('.abilityCard').count(), 4);
      assert.doesNotMatch(await page.locator('#buildSummary').innerText(), /NaN|undefined/);
    }
    await page.locator('#resetCalculator').click();
    await page.locator('#rank1').selectOption('0');
    assert.equal(await page.locator('#quantityLabel1').innerText(), 'Exposure (seconds)');
    await page.locator('#quantity1').fill('3');
    assert.match(await page.locator('#abilityResult1').innerText(), /90/);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await page.screenshot({ path: require('node:path').join(require('node:os').tmpdir(), 'deadlock-damage-mobile.png'), fullPage: true });
    await page.locator('#browseInventory').click();
    assert.ok(await page.locator('#inventoryModal').evaluate(el => el.scrollWidth <= el.clientWidth));
    assert.ok(await page.locator('#inventoryResults').evaluate(el => el.scrollWidth <= el.clientWidth));
    await page.screenshot({ path: require('node:path').join(require('node:os').tmpdir(), 'deadlock-inventory-mobile.png') });
    await page.locator('#closeInventory').click();
    assert.deepEqual(errors, []);
    console.log('Browser checks passed: target damage, items, persistence, AP, validation, 38 heroes, DPS exposure, mobile layout.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
