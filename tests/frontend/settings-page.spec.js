// End-to-end tests of the settings page against the real controller (fake panel).
const { test, expect } = require('@playwright/test');

const config = async (request) => (await request.get('/api/config')).json();
const health = async (request) => (await request.get('/api/health')).json();
const TOKEN = 'settings-test-token';
const withToken = { headers: { 'X-PixelPane-Token': TOKEN } };

test.beforeEach(async ({ page, request }) => {
  await request.put('/api/config', { ...withToken, data: { schedule: [], api_token: null } });
  await request.post('/api/state', { data: { power: true, brightness: 60 } });
  page.errors = [];
  page.on('pageerror', (e) => page.errors.push(e.message));
  page.on('console', (m) => m.type() === 'error' && page.errors.push(m.text()));
  await page.goto('/settings');
  await expect(page.locator('#stat')).toContainText('dev');
});

test.afterEach(async ({ page, request }) => {
  await request.put('/api/config', { ...withToken, data: { schedule: [], api_token: null } });
  expect(page.errors, 'browser errors').toEqual([]);
});

test('quiet hours: add, save, and the board follows them', async ({ page, request }) => {
  await expect(page.getByTestId('rule')).toHaveCount(0);
  await page.getByTestId('rule-preset').selectOption('quiet');
  await page.getByTestId('add-rule').click();
  const rule = page.getByTestId('rule');
  await expect(rule).toHaveCount(1);
  // make it cover right now, whatever time the test runs
  const now = new Date(), hhmm = (d) => d.toTimeString().slice(0, 5);
  await rule.getByLabel('From').fill(hhmm(new Date(now - 60 * 60_000)));
  await rule.getByLabel('To').fill(hhmm(new Date(+now + 60 * 60_000)));
  await page.getByTestId('save-schedule').click();
  await expect(page.locator('#toast')).toContainText('Schedule saved');
  const saved = (await config(request)).schedule;
  expect(saved).toHaveLength(1);
  expect(saved[0]).toMatchObject({ label: 'Quiet hours', action: 'off', days: [0, 1, 2, 3, 4, 5, 6] });
  await expect.poll(async () => (await health(request)).schedule.off).toBe(true);
  await expect.poll(async () => (await health(request)).scene).toBe('scheduled off');
  await expect(page.getByTestId('schedule-now')).toContainText('off until');

  // the control page shows it, and Power turns the board on anyway
  await page.goto('/');
  await expect(page.getByTestId('schedule-status')).toContainText('Scheduled off until');
  await expect(page.locator('#power')).toHaveText('Power: OFF (schedule)');
  await page.locator('#power').click();
  await expect.poll(async () => (await health(request)).on).toBe(true);
  await expect(page.getByTestId('schedule-status')).toContainText('On anyway');
});

test('a dim rule and a playlist rule round-trip', async ({ page, request }) => {
  await page.getByTestId('rule-preset').selectOption('dim');
  await page.getByTestId('add-rule').click();
  await page.getByTestId('rule-preset').selectOption('playlist');
  await page.getByTestId('add-rule').click();
  const rules = page.getByTestId('rule');
  await rules.nth(1).getByRole('button', { name: /^Sat/ }).click();   // add Saturday
  await rules.nth(1).getByLabel('Scenes in order').fill('clock, moon');
  await rules.nth(1).getByLabel('Scenes in order').dispatchEvent('change');
  await page.getByTestId('save-schedule').click();
  await expect(page.locator('#toast')).toContainText('Schedule saved');
  const [dim, list] = (await config(request)).schedule;
  expect(dim).toMatchObject({ action: 'dim', brightness: 20, from: '20:00', to: '23:00' });
  expect(list).toMatchObject({ action: 'playlist', rotation: ['clock', 'moon'], days: [0, 1, 2, 3, 4, 5] });
  // bad scenes are refused with the server's message
  await rules.nth(1).getByLabel('Scenes in order').fill('clock, nope');
  await rules.nth(1).getByLabel('Scenes in order').dispatchEvent('change');
  await page.getByTestId('save-schedule').click();
  await expect(page.locator('#toast')).toContainText('nope');
  page.errors = page.errors.filter((e) => !e.includes('400'));   // that refusal was the point
  await rules.nth(0).getByTestId('delete-rule').click();
  await expect(rules).toHaveCount(1);
});

test('seconds per scene and display settings save', async ({ page, request }) => {
  const clock = page.getByTestId('dwell-clock');
  await clock.fill('7');
  await clock.dispatchEvent('change');
  await expect.poll(async () => (await config(request)).dwell.clock).toBe(7);
  await page.locator('#hw-gpio_slowdown').fill('2');
  await page.getByTestId('save-display').click();
  await expect(page.locator('#toast')).toContainText('restart to apply');
  expect((await config(request)).gpio_slowdown).toBe(2);
  await request.put('/api/config', { data: { dwell: { clock: 10 }, gpio_slowdown: null } });
});

test('token: set it, the page keeps working, turn it off', async ({ page, request }) => {
  await expect(page.locator('#tokstate')).toContainText('No token');
  await page.getByTestId('token-input').fill(TOKEN);
  await page.getByTestId('set-token').click();
  await expect(page.locator('#tokstate')).toContainText('A token is set');
  expect((await request.post('/api/skip')).status()).toBe(401);            // others need it now
  await page.getByTestId('clear-token').click();                          // this browser remembered it
  await expect(page.locator('#tokstate')).toContainText('No token');
  expect((await request.post('/api/skip')).status()).toBe(200);
});

test('backup downloads, restores and system shows status and logs', async ({ page, request }) => {
  await request.put('/api/config', { data: { allowed_hosts: ['pane.example.com'] } });
  await page.reload();
  await expect(page.getByTestId('allowed-hosts')).toHaveValue('pane.example.com');
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByTestId('download-backup').click()]);
  expect(download.suggestedFilename()).toMatch(/^pixelpane-settings-\d{8}-\d{4}\.json$/);
  const file = await download.path();
  await request.put('/api/config', { data: { allowed_hosts: [] } });
  await page.getByTestId('restore-file').setInputFiles(file);
  await page.getByTestId('restore').click();
  await expect(page.locator('#toast')).toContainText('Settings restored');
  expect((await config(request)).allowed_hosts).toEqual(['pane.example.com']);
  await request.put('/api/config', { data: { allowed_hosts: [] } });

  await expect(page.locator('#facts')).toContainText('Version');
  await page.getByTestId('load-logs').click();
  await expect(page.getByTestId('logs')).toBeVisible();
});

test('holidays: your own, built-ins switched off, and the southern hemisphere', async ({ page, request }) => {
  const today = new Date();
  const mmdd = `${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  try {
    await page.getByTestId('add-holiday').click();
    const row = page.getByTestId('holiday');
    await row.locator('input').fill('Test Day');
    await row.locator('textarea').fill(mmdd);   // one day: today, every year
    await page.getByTestId('builtin-holidays').getByLabel('Fourth of July').uncheck();
    await page.getByTestId('hemisphere').selectOption('south');
    await page.getByTestId('save-holidays').click();
    await expect(page.locator('#toast')).toContainText('Holidays saved');
    const { themes } = await config(request);
    expect(themes).toEqual({ hemisphere: 'south', off: ['july4'],
      custom: [{ key: 'test_day', name: 'Test Day', dates: [[mmdd, mmdd]] }] });
    expect((await health(request)).themes).toContain('test_day');
    // GIFs can go in it: the GIFs page offers it as a theme
    await page.goto('/library');
    await expect(page.getByTestId('upload-theme').locator('option[value="test_day"]')).toHaveText('Test Day');
    await page.goto('/settings');
    await expect(page.getByTestId('holiday').locator('textarea')).toHaveValue(mmdd);
    // a bad date is refused with the reason
    await page.getByTestId('holiday').locator('textarea').fill('02-30');
    await page.getByTestId('save-holidays').click();
    await expect(page.locator('#toast')).toContainText('not a real date');
    page.errors = page.errors.filter((e) => !e.includes('400'));   // the expected refusal
  } finally {
    await request.put('/api/config', { data: { themes: { hemisphere: 'north', off: [], custom: [] } } });
  }
});

test('appearance: light theme and an accent color repaint every page', async ({ page, request }) => {
  try {
    await page.getByTestId('ui-theme').selectOption('light');
    await page.getByTestId('ui-accent').fill('#1d4ed8');
    await page.getByTestId('save-appearance').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    const look = () => page.evaluate(() => {
      const css = getComputedStyle(document.documentElement);
      return [css.getPropertyValue('--accent').trim(), css.getPropertyValue('--on-accent').trim(), getComputedStyle(document.body).backgroundColor];
    });
    expect(await look()).toEqual(['#1d4ed8', '#ffffff', 'rgb(244, 244, 242)']);   // white text on a dark accent
    await page.goto('/');
    expect(await look()).toEqual(['#1d4ed8', '#ffffff', 'rgb(244, 244, 242)']);
    expect((await request.put('/api/config', { data: { ui: { accent: 'blue' } } })).status()).toBe(400);
  } finally {
    await request.put('/api/config', { data: { ui: { theme: 'dark', accent: '#fdae84' } } });
  }
});

test('on screen: add two overlays, fields follow the choice, save, remove', async ({ page, request }) => {
  await request.put('/api/config', { data: { plugins: { effects: { overlays: [] } } } });
  await page.reload();
  const section = page.getByTestId('onscreen');
  await expect(section).toBeVisible();
  await page.getByTestId('sf-effects-overlays-add').click();
  await page.getByTestId('sf-effects-overlays-add').click();
  const cards = section.locator('.item');
  await expect(cards).toHaveCount(2);
  const first = cards.nth(0);
  await expect(first.getByLabel('Tile label')).toBeHidden();          // only for readings
  await first.getByLabel('Show', { exact: true }).selectOption('reading');
  await expect(first.getByLabel('Tile label')).toBeVisible();
  await first.getByLabel('Reading').selectOption('co2');
  await first.getByLabel('Tile label').fill('office');
  await first.getByLabel('Corner').selectOption('bottom_right');
  await cards.nth(1).getByLabel('Show', { exact: true }).selectOption('text');
  await cards.nth(1).getByLabel('Text', { exact: true }).fill('hi joe');
  await page.getByTestId('save-plugin-effects').click();
  await expect(page.locator('#toast')).toContainText('effects saved');
  let o = (await config(request)).plugins.effects.overlays;
  expect(o.map(x => x.show)).toEqual(['reading', 'text']);
  expect([o[0].reading, o[0].label, o[0].corner, o[1].text]).toEqual(['co2', 'office', 'bottom_right', 'hi joe']);
  await cards.nth(1).getByRole('button', { name: 'Remove this overlay' }).click();
  await expect(cards).toHaveCount(1);
  const saved = page.waitForResponse(r => r.url().endsWith('/api/config') && r.request().method() === 'PUT');
  await page.getByTestId('save-plugin-effects').click();
  await saved;
  o = (await config(request)).plugins.effects.overlays;
  expect(o.map(x => x.show)).toEqual(['reading']);
  await request.put('/api/config', { data: { plugins: { effects: { overlays: [] } } } });
});

test('notifications: a reminder saves, the style saves and test buttons send', async ({ page, request }) => {
  const reset = { plugins: { triggers: { reminders: [], watches: [] }, alerts: { style: 'classic' } } };
  await request.put('/api/config', { data: reset });
  await page.reload();
  try {
    const section = page.getByTestId('notifications');
    await expect(section).toBeVisible();
    await section.locator('#sf-alerts-style').selectOption('banner');
    await page.getByTestId('save-plugin-alerts').click();
    await expect(page.locator('#toast')).toContainText('alerts saved');
    expect((await config(request)).plugins.alerts.style).toBe('banner');

    await page.getByTestId('sf-triggers-reminders-add').click();
    const card = section.locator('#sf-triggers-reminders .item').first();
    await card.getByLabel('Text').fill('Bins out');
    await card.getByLabel('Time').fill('19:30');
    await card.getByLabel('sat').uncheck();
    await card.getByLabel('sun').uncheck();
    // a watch shows its label box only for readings, and its value only when it compares
    await page.getByTestId('sf-triggers-watches-add').click();
    const watch = section.locator('#sf-triggers-watches .item').first();
    await expect(watch.getByLabel('Reading label')).toBeVisible();
    await watch.getByLabel('When').selectOption('now_playing.title');
    await expect(watch.getByLabel('Reading label')).toBeHidden();
    await watch.getByLabel('Condition').selectOption('changes');
    await expect(watch.getByLabel('Value')).toBeHidden();
    await page.getByTestId('save-plugin-triggers').click();
    await expect(page.locator('#toast')).toContainText('triggers saved');
    const saved = (await config(request)).plugins.triggers;
    expect(saved.reminders).toEqual([expect.objectContaining({ text: 'Bins out', time: '19:30',
      days: ['mon', 'tue', 'wed', 'thu', 'fri'], icon: 'bell' })]);
    expect(saved.watches[0]).toMatchObject({ when: 'now_playing.title', op: 'changes' });

    // a bad time is refused with a message, and nothing changes
    await card.getByLabel('Time').fill('7pm');
    await page.getByTestId('save-plugin-triggers').click();
    await expect(page.locator('#toast')).toContainText('HH:MM');
    expect((await config(request)).plugins.triggers.reminders[0].time).toBe('19:30');
    page.errors = [];   // that refused save logged its 400 on purpose

    await page.getByTestId('test-notification').click();
    await expect(page.locator('#toast')).toContainText('Sent');
  } finally {
    await request.put('/api/config', { data: reset });
  }
});

test('notifications: write a message and send it, keep one on screen, clear it', async ({ page, request }) => {
  const box = page.getByTestId('composer');
  await expect(box).toBeVisible();
  await box.getByTestId('compose-send').click();
  await expect(page.locator('#toast')).toContainText('Write a message first');
  await box.getByLabel('Message').fill('Dinner is ready');
  await box.getByLabel('Second line').fill('come down');
  await box.getByLabel('Icon').selectOption('heart');
  await box.getByLabel('Style').selectOption('banner');
  const sent = page.waitForRequest(r => r.url().endsWith('/api/notify') && r.method() === 'POST');
  await box.getByTestId('compose-send').click();
  const body = (await sent).postDataJSON();
  expect([body.text, body.sub, body.icon, body.style]).toEqual(['Dinner is ready', 'come down', 'heart', 'banner']);
  await expect.poll(async () => (await health(request)).scene).toBe('notify');

  await box.getByTestId('compose-pin').click();
  await expect.poll(async () => (await health(request)).pinned?.scene).toBe('message');
  await box.getByTestId('compose-clear').click();
  await expect.poll(async () => (await health(request)).pinned).toBeNull();
});

test('every section link jumps to its section', async ({ page }) => {
  const links = page.getByRole('navigation', { name: 'Sections' }).getByRole('link');
  const targets = await links.evaluateAll((els) => els.map((a) => a.getAttribute('href')));
  expect(targets.length).toBe(11);
  for (const href of targets) {
    await page.getByRole('navigation', { name: 'Sections' }).locator(`a[href="${href}"]`).click();
    await expect(page).toHaveURL(new RegExp(`${href}$`));
    await expect(page.locator(href)).toBeInViewport();
  }
});

test('Default puts the accent color back without saving', async ({ page, request }) => {
  const before = (await config(request)).ui;
  await page.getByTestId('ui-accent').fill('#123456');
  await page.getByTestId('ui-default').click();
  await expect(page.getByTestId('ui-accent')).toHaveValue('#fdae84');
  expect((await config(request)).ui).toEqual(before);
});

test('Restart PixelPane, and Save and restart, wait for the board to come back', async ({ page, request }) => {
  // the real restart would end the test server, so the board's answer is stood in for
  let restarts = 0;
  await page.route('**/api/system/restart', (route) => { restarts += 1; route.fulfill({ json: { ok: true } }); });
  await page.getByTestId('restart').click();
  await expect(page.locator('#toast')).toHaveText('Restarting…');
  await expect(page.locator('#toast')).toHaveText('Back up', { timeout: 10_000 });
  try {
    await page.locator('#hw-gpio_slowdown').fill('3');
    await page.getByTestId('restart-display').click();
    await expect(page.locator('#toast')).toHaveText('Restarting…');
    await expect(page.locator('#toast')).toHaveText('Back up', { timeout: 10_000 });
    expect((await config(request)).gpio_slowdown).toBe(3);
    expect(restarts).toBe(2);
  } finally {
    await request.put('/api/config', { data: { gpio_slowdown: null } });
  }
});

test('allowed host names save', async ({ page, request }) => {
  try {
    await page.getByTestId('allowed-hosts').fill('pane.example.com\n\n  board.lan  ');
    await page.getByTestId('save-hosts').click();
    await expect.poll(async () => (await config(request)).allowed_hosts).toEqual(['pane.example.com', 'board.lan']);
  } finally {
    await request.put('/api/config', { data: { allowed_hosts: [] } });
  }
});

test('the log can show only warnings and errors', async ({ page, request }) => {
  await request.post('/api/play', { data: { scene: 'no_such_scene' } });   // logs a warning, maybe
  await page.getByTestId('load-logs').click();
  const lines = page.getByTestId('logs').locator('div');
  await expect(lines.first()).toBeVisible();
  const levels = () => lines.evaluateAll((els) => els.map((e) => e.className));
  expect(await levels()).toContain('INFO');
  await page.locator('#onlyproblems').check();
  await expect.poll(async () => (await levels()).filter((l) => l === 'INFO' || l === 'DEBUG')).toEqual([]);
  await page.locator('#onlyproblems').uncheck();
  await expect.poll(levels).toContain('INFO');
  page.errors = page.errors.filter((e) => !e.includes('400'));
});

test('the live preview folds away and back', async ({ page }) => {
  const box = page.getByTestId('mini-preview');
  await expect(box.locator('canvas')).toBeVisible();
  await box.locator('summary').click();
  await expect(box.locator('canvas')).toBeHidden();
  await box.locator('summary').click();
  await expect(box.locator('canvas')).toBeVisible();
});

test('Show a GIF now and Try the reminders send to the board', async ({ page, request }) => {
  const reset = { plugins: { triggers: { reminders: [], watches: [] } } };
  await request.put('/api/config', { data: reset });
  // a notification from an earlier test always plays to the end: wait it out
  await expect.poll(async () => (await health(request)).scene, { timeout: 30_000 }).not.toBe('notify');
  await page.reload();
  try {
    await page.getByTestId('effects-try').click();
    await expect(page.locator('#toast')).toContainText('Playing a GIF');
    await expect.poll(async () => (await health(request)).scene).toMatch(/^gif: /);

    await page.getByTestId('test-reminders').click();
    await expect(page.locator('#toast')).toContainText('Add a reminder with some text first');
    await page.getByTestId('sf-triggers-reminders-add').click();
    await page.locator('#sf-triggers-reminders .item').first().getByLabel('Text').fill('Water plants');
    const sent = page.waitForRequest((r) => r.url().endsWith('/api/notify') && r.method() === 'POST');
    await page.getByTestId('test-reminders').click();
    expect((await sent).postDataJSON().text).toBe('Water plants');
    await expect(page.locator('#toast')).toHaveText('Sent');
  } finally {
    await request.put('/api/config', { data: reset });
  }
});

test('a plugin switches off and on from its settings', async ({ page, request }) => {
  const enabled = async () => (await (await request.get('/api/state')).json()).plugins.find((p) => p.name === 'generative').enabled;
  try {
    await page.locator('#plugin-generative > summary').click();   // folded until opened
    await expect(page.getByTestId('toggle-generative')).toHaveText('On');
    await page.getByTestId('toggle-generative').click();
    await expect(page.getByTestId('toggle-generative')).toHaveText('Off');
    await expect(page.locator('#plugin-generative')).toContainText('is switched off');
    expect(await enabled()).toBe(false);
    await page.getByTestId('toggle-generative').click();
    await expect(page.getByTestId('toggle-generative')).toHaveText('On');
    expect(await enabled()).toBe(true);
    // previews still loading when it went off are refused while it's off
    page.errors = page.errors.filter((e) => !e.includes('404'));
  } finally {
    await request.put('/api/config', { data: { plugins: { generative: { enabled: true } } } });
  }
});

test('a rule keeps its name and can be switched off', async ({ page, request }) => {
  await page.getByTestId('rule-preset').selectOption('dim');
  await page.getByTestId('add-rule').click();
  const rule = page.getByTestId('rule');
  await rule.getByPlaceholder('Name (optional)').fill('Evening dim');
  await rule.getByLabel('on', { exact: true }).uncheck();
  await expect(rule).toHaveClass(/off/);
  await page.getByTestId('save-schedule').click();
  await expect(page.locator('#toast')).toContainText('Schedule saved');
  expect((await config(request)).schedule[0]).toMatchObject({ label: 'Evening dim', enabled: false, action: 'dim' });
});

test('a holiday you added can be deleted', async ({ page, request }) => {
  try {
    await page.getByTestId('add-holiday').click();
    await page.getByTestId('add-holiday').click();
    await expect(page.getByTestId('holiday')).toHaveCount(2);
    await page.getByTestId('holiday').first().getByTestId('delete-holiday').click();
    await expect(page.getByTestId('holiday')).toHaveCount(1);
  } finally {
    await request.put('/api/config', { data: { themes: { hemisphere: 'north', off: [], custom: [] } } });
  }
});
