// End-to-end tests of the control page against the real controller (fake panel).
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
  const preview = page.locator('#preview');
  await expect.poll(() => preview.evaluate((img) => img.naturalWidth)).toBe(320);
  const first = await preview.getAttribute('src');
  await expect.poll(() => preview.getAttribute('src'), { timeout: 3000 }).not.toBe(first); // refreshes
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

test('seconds per scene saves on change', async ({ page, request }) => {
  const clock = page.locator('#dwell label', { hasText: 'clock' }).locator('input');
  await clock.fill('7');
  await clock.dispatchEvent('change');
  await expect.poll(async () => (await config(request)).dwell.clock).toBe(7);
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
