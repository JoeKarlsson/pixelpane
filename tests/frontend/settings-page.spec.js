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
