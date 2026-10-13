// End-to-end tests of the GIFs page (maker and library) against the real controller (fake panel).
const http = require('http');
const path = require('path');
const { test, expect } = require('@playwright/test');

const health = async (request) => (await request.get('/api/health')).json();
const config = async (request) => (await request.get('/api/config')).json();
const sceneIs = (request, re, timeout = 10_000) =>
  expect.poll(async () => (await health(request)).scene, { timeout, intervals: [100] }).toMatch(re);

async function pushData(request) {
  const soon = new Date(Date.now() + 30 * 60_000).toISOString();
  const data = {
    weather: { temp: 48, condition: 'sunny', high: 55, low: 40, precip: 10 },
    now_playing: { title: 'Midnight City', artist: 'M83', player: 'Office', state: 'playing' },
    next_event: { title: 'Team standup', start: soon },
    homelab: { alerts: 1, names: ['plex'], warnings: 0 },
    tiles: { items: [{ icon: 'thermometer', text: '71F office', color: '#ffaa44' }] },
  };
  for (const [key, body] of Object.entries(data)) {
    expect((await request.post(`/api/data/${key}`, { data: body })).ok()).toBeTruthy();
  }
}

test.beforeEach(async ({ page, request }) => {
  await request.post('/api/state', { data: { power: true, brightness: 60 } });
  await request.delete('/api/pin');
  // Notifications always play to the end; don't start a test under one.
  await expect.poll(async () => (await health(request)).scene, { timeout: 30_000 }).not.toBe('notify');
  page.errors = [];
  page.on('pageerror', (e) => page.errors.push(e.message));
  page.on('console', (m) => m.type() === 'error' && page.errors.push(m.text()));
  await page.goto('/library');
  await expect(page.locator('#stat')).toContainText('dev');
});

test.afterEach(async ({ page }) => {
  expect(page.errors, 'browser errors').toEqual([]);
});

test('GIFs can be moved to another category or theme, one at a time or in bulk', async ({ page, request }) => {
  const cards = page.getByTestId('gif-card');
  const dlg = page.getByTestId('classify-dialog');
  await page.getByTestId('gif-filter').selectOption('cat:space');
  await expect(cards.first().locator('.stat')).toHaveText(/^space-/);   // the list has switched
  const name = await cards.first().locator('.stat').textContent();
  await cards.first().getByTestId('classify').click();
  await expect(dlg.getByTestId('classify-category')).toHaveValue('space');
  await dlg.getByTestId('classify-category').fill('Outer Space');
  await dlg.getByTestId('classify-theme').selectOption('winter');
  await dlg.getByTestId('classify-save').click();
  await expect(page.locator('#toast')).toContainText('Moved');
  const find = async () => (await (await request.get('/api/gifs')).json()).find((g) => g.id === `repo/${name}.gif`);
  expect(await find()).toMatchObject({ category: 'outer_space', theme: 'winter', moved: true });

  await page.getByTestId('gif-filter').selectOption('winter');
  const moved = cards.filter({ hasText: name });
  await expect(moved.locator('.cat')).toHaveText(/^outer_space\b/);   // plus a play count, if the playlist played it
  await expect(moved.locator('.cat')).toHaveClass(/moved/);
  await moved.getByTestId('classify').click();
  await dlg.getByTestId('classify-reset').click();
  await expect.poll(async () => (await config(request)).gif_meta).toEqual({});

  // bulk: select the page, give every GIF a new category, then rename it back
  await page.getByTestId('gif-filter').selectOption('cat:retro');
  await expect(cards.first().locator('.stat')).toHaveText(/^retro-/);
  const n = await cards.count();
  await page.getByTestId('select-mode').click();
  await expect(page.getByTestId('bulk-bar')).toBeVisible();
  await expect(page.getByTestId('bulk-move')).toBeDisabled();
  await expect(cards.first().getByRole('button', { name: 'Play next' })).toBeHidden();   // no stray plays
  const count = page.getByTestId('selected-count');
  // click picks a card, a second click unpicks it
  await cards.nth(0).click();
  await expect(cards.nth(0)).toHaveAttribute('aria-checked', 'true');
  await expect(count).toHaveText('1 selected');
  await cards.nth(0).click();
  await expect(cards.nth(0)).toHaveClass(/selecting/);
  await expect(cards.nth(0)).not.toHaveClass(/picked/);
  await expect(count).toHaveText('Click GIFs to pick them');
  // shift-click picks the range in between
  await cards.nth(0).click();
  await cards.nth(n - 1).click({ modifiers: ['Shift'] });
  await expect(count).toHaveText(`${n} selected`);
  await expect(page.getByTestId('select-page')).toHaveText('Unselect page');
  await page.getByTestId('select-page').click();
  await expect(count).toHaveText('Click GIFs to pick them');
  await page.getByTestId('select-page').click();
  await page.getByTestId('select-clear').click();
  await expect(count).toHaveText('Click GIFs to pick them');
  await page.getByTestId('select-page').click();
  await expect(count).toHaveText(`${n} selected`);
  await page.getByTestId('bulk-move').click();
  await dlg.getByTestId('classify-category').fill('arcade');
  await dlg.getByTestId('classify-save').click();
  await expect(page.locator('#toast')).toContainText(`Moved ${n} GIFs`);
  const arcade = (await (await request.get('/api/gifs')).json()).filter((g) => g.category === 'arcade');
  expect(arcade.map((g) => g.theme)).toEqual(Array(n).fill('all'));   // bulk kept each GIF's theme
  await expect(count).toHaveText('Click GIFs to pick them');

  await page.getByTestId('gif-filter').selectOption('cat:arcade');
  await expect(cards).toHaveCount(n);
  await page.getByTestId('rename-category').click();
  await page.getByTestId('rename-input').fill('retro');
  await page.getByTestId('rename-save').click();
  await expect(page.locator('#toast')).toContainText(`Renamed ${n} GIFs`);
  await expect.poll(async () => (await config(request)).gif_meta).toEqual({});
  await expect(page.getByTestId('gif-filter')).toHaveValue('cat:retro');
  await expect(cards).toHaveCount(n);
  await page.getByTestId('select-mode').click();   // now reads Done
  await expect(page.getByTestId('bulk-bar')).toBeHidden();
  await expect(cards.first().getByRole('button', { name: 'Play next' })).toBeVisible();
});

test('GIF library filters by category and theme, hides and plays', async ({ page, request }) => {
  const cards = page.getByTestId('gif-card');
  const all = (await (await request.get('/api/gifs')).json());
  await expect(cards).toHaveCount(all.length);                              // Everything by default
  await expect(page.getByTestId('gif-filter').locator('option[value="everything"]')).toHaveText(`Everything (${all.length})`);
  await expect(cards.filter({ hasText: 'halloween' }).first().locator('.theme')).toHaveText('halloween');
  await page.getByTestId('gif-filter').selectOption('all');
  await expect(cards).toHaveCount(all.filter((g) => g.theme === 'all').length);
  await expect(page.getByTestId('gif-filter').locator('option[value="halloween"]'))
    .toHaveText(new RegExp(`\\(${all.filter((g) => g.theme === 'halloween').length}\\)$`));

  await page.getByTestId('gif-filter').selectOption('cat:retro');
  await expect(cards).toHaveCount(all.filter((g) => g.category === 'retro' && g.theme === 'all').length);
  const names = await cards.locator('.stat').allTextContents();
  expect(names.every((n) => n.startsWith('retro-'))).toBeTruthy();

  await page.getByTestId('gif-filter').selectOption('halloween');
  await expect(cards).toHaveCount(all.filter((g) => g.theme === 'halloween').length);

  await page.getByTestId('gif-filter').selectOption('cat:space');
  await expect(cards.first().locator('.stat')).toHaveText(/^space-/);   // the list has switched
  const card = cards.first();
  const name = await card.locator('.stat').textContent();
  await card.getByRole('button', { name: 'hide' }).click();
  await expect(cards.first()).toHaveClass(/hidden/);
  await expect.poll(async () => (await config(request)).hidden_gifs).toContain(`repo/${name}.gif`);
  await cards.first().getByRole('button', { name: 'show' }).click();
  await expect.poll(async () => (await config(request)).hidden_gifs).not.toContain(`repo/${name}.gif`);

  await cards.first().getByRole('button', { name: 'Play next' }).click();
  await sceneIs(request, new RegExp(`^gif: ${name}\\.gif$`));
});

test('upload to a theme, then delete it', async ({ page, request }) => {
  await page.getByRole('button', { name: 'Upload' }).click();
  await expect(page.locator('#toast')).toContainText('Pick a file first');

  await page.getByTestId('upload-theme').selectOption('winter');
  await page.locator('#gfile').setInputFiles(path.join(__dirname, 'fixtures', 'test-sprite.gif'));
  await page.getByRole('button', { name: 'Upload' }).click();
  await expect(page.locator('#toast')).toContainText('Uploaded');

  await page.getByTestId('gif-filter').selectOption('winter');
  const mine = page.getByTestId('gif-card').filter({ hasText: 'test-sprite' });
  await expect(mine).toHaveCount(1);
  await expect.poll(() => mine.locator('img').evaluate((img) => img.naturalWidth)).toBe(32); // converted
  await mine.getByRole('button', { name: 'Delete' }).click();   // the first click only arms it
  await expect(mine.getByRole('button', { name: 'Confirm delete' })).toBeVisible();
  await mine.getByRole('button', { name: 'Confirm delete' }).click();
  await expect(page.locator('#toast')).toContainText('Deleted');
  await expect(mine).toHaveCount(0);
});

test('GIF library pages through big libraries', async ({ page, request }) => {
  const total = (await (await request.get('/api/gifs')).json()).length;
  expect(total).toBeGreaterThan(60);
  const cards = page.getByTestId('gif-card');
  await page.getByTestId('page-size').selectOption('60');
  await expect(cards).toHaveCount(60);
  await expect(page.locator('#gpage')).toHaveText(new RegExp(`^Page 1 of 2 · 1-60$`));
  await expect(page.locator('#gprev')).toBeDisabled();
  await page.locator('#gnext').click();
  await expect(cards).toHaveCount(total - 60);
  await expect(page.locator('#gnext')).toBeDisabled();
  await page.getByTestId('gif-filter').selectOption('halloween');        // a new filter starts on page 1
  await expect(page.locator('#gpage')).toHaveText(/^Page 1 of 1/);
  await page.getByTestId('gif-filter').selectOption('everything');
  await page.getByTestId('page-size').selectOption('300');
  await expect(cards).toHaveCount(total);
});

test('Make a GIF: drafts are previewed, refined, saved or discarded', async ({ page, request }) => {
  // a stand-in for the model server: always designs the same little animation
  const spec = { name: 'Bouncy Ball', category: 'toys', seconds: 1, fps: 8, background: '#000000',
    layers: [{ type: 'circle', x: 16, y: 16, r: 5, color: '#ff4060', motion: { bob: 4 } }] };
  const stub = http.createServer((req, res) => {
    req.resume();
    req.on('end', () => {
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ choices: [{ message: { content: JSON.stringify(spec) } }] }));
    });
  });
  await new Promise((r) => stub.listen(0, '127.0.0.1', r));
  const library = async () => (await (await request.get('/api/gifs')).json()).filter((g) => g.upload);
  try {
    await expect(page.getByTestId('generate-setup')).toBeVisible();          // not set up yet
    await expect(page.getByTestId('generate')).toBeDisabled();
    await request.put('/api/config', { data: { plugins: { generator: {
      base_url: `http://127.0.0.1:${stub.address().port}/v1`, model: 'stub', review: false } } } });
    await page.reload();
    await page.getByTestId('generate').click();
    await expect(page.locator('#toast')).toContainText('Type an idea');
    await page.getByTestId('generate-prompt').fill('a bouncy ball');
    await page.getByTestId('generate').click();

    const draft = page.getByTestId('draft');
    await expect(draft).toBeVisible({ timeout: 15_000 });
    await expect(draft).toContainText('Bouncy Ball');
    await expect(draft).toContainText('"a bouncy ball"');
    await expect.poll(() => draft.locator('img').evaluate((img) => img.naturalWidth)).toBe(32);
    expect(await library()).toEqual([]);                                     // nothing saved yet
    await expect(page.getByTestId('draft-thumb')).toHaveCount(1);

    await page.getByTestId('draft-play').click();                            // see it on the panel first
    await sceneIs(request, /^gif: [0-9a-f]{12}\.gif$/);

    await page.getByTestId('draft-change').fill('make it blue');
    await page.getByTestId('draft-refine').click();
    await expect(page.getByTestId('draft-thumb')).toHaveCount(2, { timeout: 15_000 });
    await expect(draft).toContainText('changed: make it blue');

    await page.getByTestId('draft-name').fill('Blue Ball');
    await page.getByTestId('draft-category').fill('toys');
    await page.getByTestId('draft-theme').selectOption('winter');
    await page.getByTestId('draft-save').click();
    await expect(page.locator('#toast')).toContainText('Saved to the library as toys-blue-ball.gif');
    await expect(page.getByTestId('draft-saved')).toContainText('toys-blue-ball.gif');
    expect((await library()).map((g) => [g.name, g.theme])).toEqual([['toys-blue-ball.gif', 'winter']]);
    await expect(page.locator('.draft-thumb.saved')).toHaveCount(1);

    // the older draft: open it from the strip and throw it away
    await page.getByTestId('draft-thumb').nth(1).click();
    await expect(draft).not.toContainText('changed:');
    await page.getByTestId('draft-discard').click();
    await expect(draft).toBeHidden();
    await expect(page.getByTestId('draft-thumb')).toHaveCount(1);

    // the saved one shows up first in the library (newest first) and under Mine
    await page.getByTestId('gif-filter').selectOption('mine');
    await expect(page.getByTestId('gif-card')).toHaveCount(1);
    await expect(page.getByTestId('gif-card').first()).toContainText('toys-blue-ball');
    await request.delete('/api/gifs/upload/winter/toys-blue-ball.gif');
  } finally {
    for (const d of await (await request.get('/api/drafts')).json()) await request.delete(`/api/drafts/${d.id}`);
    await request.put('/api/config', { data: { plugins: { generator: { base_url: '', model: '' } } } });
    stub.close();
  }
});

test('library sorts, searches, filters and resizes', async ({ page, request }) => {
  const cards = page.getByTestId('gif-card');
  const names = async () => (await cards.locator('.stat').allTextContents());
  await page.getByTestId('gif-sort').selectOption('name');
  await expect.poll(async () => (await names())[0]).toBe('abstract-dot-00');
  await page.getByTestId('gif-sort').selectOption('namedesc');
  await expect.poll(async () => (await names())[0]).not.toBe('abstract-dot-00');
  const sorted = await names();
  expect([...sorted].sort().reverse()).toEqual(sorted);
  await page.getByTestId('gif-sort').selectOption('theme');
  await expect.poll(async () => (await cards.last().locator('.theme').textContent())).toBe('halloween');
  // played GIFs climb the Most played sort
  await request.post('/api/play', { data: { scene: 'gif', params: { id: 'repo/space-purple-blink.gif' } } });
  await sceneIs(request, /^gif: space-purple-blink\.gif$/);
  await page.reload();
  await page.getByTestId('gif-sort').selectOption('most');
  const gifs = await (await request.get('/api/gifs')).json();
  expect(gifs.find((g) => g.name === 'space-purple-blink.gif').plays).toBeGreaterThan(0);
  const top = Math.max(...gifs.map((g) => g.plays));
  await expect(cards.first().locator('.cat')).toContainText(`▶${top}`);         // most played first, once it re-sorts
  const firstName = await cards.first().locator('.stat').textContent();
  expect(gifs.find((g) => g.name === firstName + '.gif').plays).toBe(top);
  // search by words in the name, category or theme
  await page.getByTestId('gif-search').fill('purple');
  await expect(cards).toHaveCount(1);
  await page.getByTestId('gif-search').fill('');
  // hidden filter
  await request.post('/api/gifs/hide', { data: { id: 'repo/retro-red-blink.gif', hidden: true } });
  await page.reload();
  await page.getByTestId('gif-filter').selectOption('hidden');
  await expect(cards).toHaveCount(1);
  await request.post('/api/gifs/hide', { data: { id: 'repo/retro-red-blink.gif', hidden: false } });
  // thumbnail size, remembered
  await page.getByTestId('gif-thumb').selectOption('112');
  await expect.poll(() => cards.first().locator('img').evaluate((i) => i.getBoundingClientRect().width)).toBe(112);
  await page.reload();
  await expect(page.getByTestId('gif-thumb')).toHaveValue('112');
  await expect(page.getByTestId('gif-sort')).toHaveValue('most');
  await page.getByTestId('gif-thumb').selectOption('64');
  await page.getByTestId('gif-sort').selectOption('newest');
});

test('Cancel closes the move and rename dialogs without changing anything', async ({ page, request }) => {
  const before = (await config(request)).gif_meta;
  await page.getByTestId('gif-filter').selectOption('cat:space');
  const cards = page.getByTestId('gif-card');
  await expect(cards.first().locator('.stat')).toHaveText(/^space-/);
  await cards.first().getByTestId('classify').click();
  const dlg = page.getByTestId('classify-dialog');
  await expect(dlg).toBeVisible();
  await dlg.getByTestId('classify-category').fill('nowhere');
  await page.locator('#gdlgcancel').click();
  await expect(dlg).toBeHidden();

  await page.getByTestId('rename-category').click();
  await expect(page.getByTestId('rename-input')).toBeVisible();
  await page.getByTestId('rename-input').fill('nowhere');
  await page.locator('#rdlgcancel').click();
  await expect(page.getByTestId('rename-input')).toBeHidden();
  expect((await config(request)).gif_meta).toEqual(before);
  expect((await (await request.get('/api/gifs')).json()).some((g) => g.category === 'nowhere')).toBe(false);
});

test('upload with smooth on fills the panel instead of fitting it with black bars', async ({ page, request }) => {
  const upload = async (smooth) => {
    await page.locator('#gfile').setInputFiles(path.join(__dirname, 'fixtures', 'wide-photo.gif'));
    await page.locator('#gsmooth').setChecked(smooth);
    await page.locator('#gup').click();
    await expect(page.locator('#toast')).toContainText('Uploaded');
    let mine;
    await expect.poll(async () => {
      mine = (await (await request.get('/api/gifs')).json()).find((g) => g.upload && g.name.includes('wide-photo'));
      return !!mine;
    }).toBe(true);
    const card = page.getByTestId('gif-card').filter({ hasText: 'wide-photo' });
    await expect.poll(() => card.locator('img').evaluate((img) => img.naturalWidth)).toBe(32);
    const bytes = await (await request.get(`/gif/${mine.id}`)).body();
    await request.delete(`/api/gifs/${mine.id}`);
    await page.reload();
    return bytes.toString('base64');
  };
  const sharp = await upload(false);
  const smooth = await upload(true);
  expect(smooth).not.toEqual(sharp);
});

test('Surprise me and Try again make new drafts', async ({ page, request }) => {
  const spec = { name: 'Surprise', category: 'toys', seconds: 1, fps: 8, background: '#000000',
    layers: [{ type: 'circle', x: 16, y: 16, r: 5, color: '#40ff60', motion: { bob: 4 } }] };
  const prompts = [];
  const stub = http.createServer((req, res) => {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      prompts.push(body);
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ choices: [{ message: { content: JSON.stringify(spec) } }] }));
    });
  });
  await new Promise((r) => stub.listen(0, '127.0.0.1', r));
  try {
    await request.put('/api/config', { data: { plugins: { generator: {
      base_url: `http://127.0.0.1:${stub.address().port}/v1`, model: 'stub', review: false } } } });
    await page.reload();
    await page.getByTestId('surprise').click();
    await expect(page.getByTestId('draft')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('draft-thumb')).toHaveCount(1);
    await page.getByTestId('draft-again').click();
    await expect(page.getByTestId('draft-thumb')).toHaveCount(2, { timeout: 15_000 });
    expect(prompts.length).toBeGreaterThanOrEqual(2);
  } finally {
    for (const d of await (await request.get('/api/drafts')).json()) await request.delete(`/api/drafts/${d.id}`);
    await request.put('/api/config', { data: { plugins: { generator: { base_url: '', model: '' } } } });
    stub.close();
  }
});
