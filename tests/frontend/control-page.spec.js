// End-to-end tests of the control page against the real controller (fake panel).
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
  await page.goto('/');
  await expect(page.locator('#stat')).toContainText('dev');
});

test.afterEach(async ({ page }) => {
  expect(page.errors, 'browser errors').toEqual([]);
});

test('page loads with status, themes and a live preview', async ({ page, request }) => {
  const h = await health(request);
  await expect(page.locator('#themes .pill')).toHaveCount(h.themes.length);
  // The preview is a canvas fed by the board's frame stream, so it moves at the panel's speed.
  await request.post('/api/pin', { data: { scene: 'plasma' } });
  const preview = page.getByTestId('preview');
  await expect.poll(() => preview.evaluate((c) => c.width)).toBe(32);
  const distinct = await preview.evaluate(async (c) => {
    const seen = new Set();
    for (let i = 0; i < 20; i++) {
      seen.add(Array.from(c.getContext('2d').getImageData(0, 0, 32, 32).data).join());
      await new Promise((r) => setTimeout(r, 50));
    }
    return seen.size;
  });
  expect(distinct).toBeGreaterThan(8);   // about one second: a 1 fps snapshot would show 1 or 2
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
  await expect(moved.locator('.cat')).toHaveText('outer_space');
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
  await expect(cards.first().getByRole('button', { name: '▶' })).toBeHidden();   // no stray plays
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
  await expect(cards.first().getByRole('button', { name: '▶' })).toBeVisible();
});

test('every Play now button plays its scene', async ({ page, request }) => {
  await pushData(request);
  const { themes } = await health(request);
  const state = await (await request.get('/api/state')).json();
  const generative = state.plugins.find((p) => p.name === 'generative').settings.scenes;
  const buttons = page.locator('[data-testid^="play-"]');
  const ids = await buttons.evaluateAll((els) => els.map((e) => e.dataset.testid.slice(5)));
  expect(ids.length).toBeGreaterThan(25);   // widgets, categories, themes and generative scenes
  for (const scene of ids) {
    await page.getByTestId(`play-${scene}`).click();
    let want;
    if (scene === 'gif') want = /^gif: /;
    else if (scene.startsWith('gif:')) want = new RegExp(`^gif: ${scene.slice(4)}-`);
    else if (scene === 'seasonal') want = new RegExp(`^(${themes.join('|')})$`);
    else if (scene === 'generative') want = new RegExp(`^(${generative.join('|')})$`);
    else want = new RegExp(`^${scene}$`);
    await sceneIs(request, want);
    await expect(page.locator('#toast')).toContainText('Up next');
  }
});

test('nothing playing just skips instead of showing a blank screen', async ({ page, request }) => {
  await request.post('/api/data/now_playing', { data: { title: '', state: 'idle' } });
  await page.getByTestId('play-now_playing').click();
  const seen = [];
  for (let k = 0; k < 15; k++) {
    seen.push((await health(request)).scene);
    await page.waitForTimeout(100);
  }
  expect(seen.filter((s) => s.includes('now_playing'))).toEqual([]);
});

test('power button turns the panel off and on', async ({ page, request }) => {
  await page.locator('#power').click();
  await expect(page.locator('#power')).toHaveText('Power: OFF');
  await sceneIs(request, /^off$/);
  await page.locator('#power').click();
  await expect(page.locator('#power')).toHaveText('Power: ON');
  await expect.poll(async () => (await health(request)).power).toBe(true);
});

test('brightness slider sets brightness', async ({ page, request }) => {
  await page.locator('#bright').fill('30');
  await expect(page.locator('#bv')).toHaveText('30');
  await expect.poll(async () => (await health(request)).brightness).toBe(30);
});

test('On Air, message and Clear', async ({ page, request }) => {
  await page.getByRole('button', { name: 'On Air' }).click();
  await expect.poll(async () => (await health(request)).pinned?.scene).toBe('on_air');
  await expect(page.locator('#scene')).toHaveText('pinned: on_air', { timeout: 7000 });
  await sceneIs(request, /^on_air$/);

  await page.locator('#msg').fill('BRB');
  await page.locator('#mins').fill('2');
  await page.getByRole('button', { name: 'Show message' }).click();
  await expect.poll(async () => (await health(request)).pinned?.params?.text).toBe('BRB');
  expect((await health(request)).pinned.until).toBeGreaterThan(Date.now() / 1000);
  await sceneIs(request, /^message$/);

  await page.getByRole('button', { name: 'Clear' }).click();
  await expect.poll(async () => (await health(request)).pinned).toBeNull();
});

test('notifications play right away', async ({ page, request }) => {
  await page.locator('#ntext').fill('Laundry is done');
  await page.locator('#nicon').selectOption('washer');
  await page.locator('#nflash').check();
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.locator('#toast')).toContainText('Sent');
  await sceneIs(request, /^notify$/);
});

test('playlist editor adds, reorders, removes and saves', async ({ page, request }) => {
  const original = (await config(request)).rotation;
  const rows = page.locator('#rot li');
  await expect(rows).toHaveCount(original.length);
  await page.locator('#addsel').selectOption('gif:space');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(rows).toHaveCount(original.length + 1);
  await expect(rows.last()).toContainText('gif:space');
  await rows.last().getByRole('button', { name: '↑' }).click();
  await expect(rows.nth(original.length - 1)).toContainText('gif:space');
  await rows.first().getByRole('button', { name: '✕' }).click();
  await page.getByRole('button', { name: 'Save playlist' }).click();
  await expect(page.locator('#toast')).toContainText('Playlist saved');
  const want = [...original.slice(1, -1), 'gif:space', original[original.length - 1]];
  await expect.poll(async () => (await config(request)).rotation).toEqual(want);
  await request.put('/api/config', { data: { rotation: original } });
});

test('the header links to settings', async ({ page }) => {
  await page.getByTestId('settings-link').click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByTestId('schedule')).toBeVisible();
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

  await cards.first().getByRole('button', { name: '▶' }).click();
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
  await mine.getByRole('button', { name: '🗑' }).click();
  await expect(page.locator('#toast')).toContainText('Deleted');
  await expect(mine).toHaveCount(0);
});

test('plugins can be switched off and on', async ({ page, request }) => {
  const row = page.getByTestId('plugin-generative');
  await expect(row.getByRole('button')).toHaveText('On');
  await row.getByRole('button').click();
  await expect(page.getByTestId('plugin-generative').getByRole('button')).toHaveText('Off');
  await expect(page.getByTestId('play-fire')).toHaveCount(0);      // its scenes leave Play now
  expect((await request.post('/api/play', { data: { scene: 'fire' } })).status()).toBe(400);
  await page.getByTestId('plugin-generative').getByRole('button').click();
  await expect(page.getByTestId('plugin-generative').getByRole('button')).toHaveText('On');
  await expect(page.getByTestId('play-fire')).toHaveCount(1);
});

test('favicon is served', async ({ page, request }) => {
  for (const url of ['/favicon.ico', '/static/favicon.svg', '/static/apple-touch-icon.png']) {
    expect((await request.get(url)).ok(), url).toBeTruthy();
  }
  await expect(page.locator('link[rel="icon"][type="image/svg+xml"]')).toHaveAttribute('href', '/static/favicon.svg');
});

test('live view shows what is on, where it came from, and highlights the playlist', async ({ page, request }) => {
  await page.getByTestId('play-plasma').click();
  await expect(page.locator('#nowsrc')).toHaveText('Requested');
  await expect(page.locator('#nowscene')).toHaveText('Plasma');

  const original = (await config(request)).rotation;
  await request.put('/api/config', { data: { rotation: ['clock', 'gif:retro'], dwell: { clock: 3, gif: 3 } } });
  await page.getByRole('button', { name: 'Skip ⏭' }).click();   // leave the requested scene now
  await expect(page.locator('#toast')).toContainText('Skipped');
  await expect(page.locator('#nowsrc')).toHaveText(/^Playlist [12]\/2$/, { timeout: 15_000 });
  const current = page.locator('#rot li.current');
  await expect(current).toHaveCount(1);
  const first = await current.getAttribute('data-index');
  await expect.poll(() => current.getAttribute('data-index'), { timeout: 10_000 }).not.toBe(first); // it moves along
  await expect(page.locator('#nowscene')).toHaveText(/^(Clock|GIF · retro · .+)$/);
  await expect(page.locator('#nownext')).toContainText('Up next in the playlist');
  await expect.poll(() => page.locator('#nowbar').evaluate((el) => parseFloat(el.style.width))).toBeGreaterThan(0);

  await request.post('/api/notify', { data: { text: 'Doorbell', seconds: 3 } });
  await expect(page.locator('#nowsrc')).toHaveText('Notification');
  await expect(page.locator('#nowscene')).toHaveText('Notification · Doorbell');
  await request.put('/api/config', { data: { rotation: original, dwell: { clock: 10, gif: 20 } } });
});

test('plugin tiles open a panel with details and editable settings', async ({ page, request }) => {
  await page.getByTestId('plugin-generative').locator('strong').click();
  const dlg = page.getByTestId('plugin-dialog');
  await expect(dlg).toBeVisible();
  await expect(dlg.locator('.about')).toContainText("Game of Life");
  await dlg.getByLabel('plasma').uncheck();
  await dlg.locator('#pd-generative').fill('9');
  await dlg.getByTestId('dlg-save').click();
  await expect(dlg).toBeHidden();
  await expect(page.locator('#toast')).toContainText('generative saved');
  let c = await config(request);
  expect(c.plugins.generative.scenes).not.toContain('plasma');
  expect(c.dwell.generative).toBe(9);

  await page.getByTestId('plugin-seasonal').locator('strong').click();
  await dlg.locator('#pf-birthday-month').selectOption('6');
  await dlg.locator('#pf-birthday-day').fill('1');
  await dlg.locator('#pf-birthday-name').fill('Robin');
  await dlg.locator('#pf-holiday_share').fill('0.5');
  await dlg.getByTestId('dlg-save').click();
  await expect(dlg).toBeHidden();
  c = await config(request);
  expect(c.plugins.seasonal.birthday).toEqual({ month: 6, day: 1, name: 'Robin' });
  expect(c.plugins.seasonal.holiday_share).toBe(0.5);

  await page.getByTestId('plugin-weather').locator('strong').click();
  await expect(dlg).toContainText('POST /api/data/weather');
  await dlg.locator('#pf-latitude').fill('51.5');
  await dlg.locator('#pf-longitude').fill('-0.12');
  await dlg.getByTestId('dlg-save').click();
  await expect(dlg).toBeHidden();
  c = await config(request);
  expect([c.plugins.weather.latitude, c.plugins.weather.longitude]).toEqual([51.5, -0.12]);

  await page.getByTestId('plugin-alerts').locator('strong').click();   // no settings: no Save
  await expect(dlg.getByTestId('dlg-save')).toHaveCount(0);
  await dlg.getByTestId('dlg-play-on_air').click();
  await expect.poll(async () => (await health(request)).scene).toBe('on_air');
  await dlg.getByTestId('dlg-close').click();
  await expect(dlg).toBeHidden();

  await request.put('/api/config', { data: { plugins: { generative: { scenes: ['fire', 'plasma', 'life', 'matrix_rain', 'starfield'] },
    seasonal: { birthday: null, holiday_share: 0.7 }, weather: { latitude: null, longitude: null } }, dwell: { generative: 25 } } });
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

test('with a token set, the page asks for it once and then works', async ({ page, request }) => {
  await request.put('/api/config', { data: { api_token: 'correct-horse' } });
  await page.reload();
  await page.evaluate(() => localStorage.removeItem('pixelpane-token'));
  await page.locator('#power').click();
  const dlg = page.getByTestId('token-dialog');
  await expect(dlg).toBeVisible();
  await page.locator('#tokinput').fill('correct-horse');
  await page.locator('#toksave').click();
  await expect(page.locator('#power')).toHaveText('Power: OFF');
  await page.locator('#power').click();                 // remembered: no second prompt
  await expect(page.locator('#power')).toHaveText('Power: ON');
  await expect(dlg).toBeHidden();
  await request.put('/api/config', { data: { api_token: null }, headers: { 'X-PixelPane-Token': 'correct-horse' } });
  await page.evaluate(() => localStorage.removeItem('pixelpane-token'));
  page.errors = page.errors.filter((e) => !e.includes('401'));   // the expected first refusal
});

test('footer links to the project on GitHub', async ({ page }) => {
  const link = page.getByTestId('github-link');
  await expect(link).toHaveAttribute('href', 'https://github.com/JoeKarlsson/pixelpane');
  await expect(link).toHaveAttribute('rel', /noopener/);
  await expect(page.locator('#footver')).toHaveText('version dev');
  const maker = page.getByTestId('maker');
  for (const [name, href] of [['Joe Karlsson', 'https://www.joekarlsson.com'], ['Newsletter', 'https://www.joekarlsson.com/newsletter'],
    ['Bluesky', 'https://bsky.app/profile/joekarlsson.com'], ['LinkedIn', 'https://www.linkedin.com/in/joekarlsson/'],
    ['YouTube', 'https://www.youtube.com/joekarlsson']]) {
    await expect(maker.getByRole('link', { name })).toHaveAttribute('href', href);
  }
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
  const firstName = await cards.first().locator('.stat').textContent();
  expect(gifs.find((g) => g.name === firstName + '.gif').plays).toBe(top);      // most played first
  await expect(cards.first().locator('.cat')).toContainText(`▶${top}`);
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
