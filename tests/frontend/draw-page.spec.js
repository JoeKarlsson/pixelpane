// End-to-end tests of the Draw and Animate pages against the real controller (fake panel).
const { test, expect } = require('@playwright/test');

const health = async (request) => (await request.get('/api/health')).json();
const sketch = async (request) => (await request.get('/api/sketch')).json();

test.beforeEach(async ({ page, request }) => {
  await request.post('/api/state', { data: { power: true, brightness: 60 } });
  await request.delete('/api/pin');
  await page.addInitScript(() => localStorage.clear());
  page.errors = [];
  page.on('pageerror', e => page.errors.push(e.message));
});

async function stroke(page, from, to) {
  const box = await page.getByTestId('draw-canvas').boundingBox();
  const at = ([x, y]) => [box.x + box.width * x, box.y + box.height * y];
  await page.mouse.move(...at(from));
  await page.mouse.down();
  await page.mouse.move(...at(to), { steps: 8 });
  await page.mouse.up();
}

test('what you draw shows on the board while you draw it', async ({ page, request }) => {
  await page.goto('/draw');
  await expect(page.getByTestId('draw-link')).toHaveAttribute('aria-current', 'page');
  await stroke(page, [0.1, 0.5], [0.9, 0.5]);
  await expect.poll(async () => (await health(request)).scene, { timeout: 10_000 }).toBe('sketch');
  await expect(page.getByTestId('draw-status')).toContainText('Showing on the board');
  const sk = await sketch(request);
  expect(sk.frames).toHaveLength(1);
  expect(Buffer.from(sk.frames[0], 'base64').some(v => v)).toBeTruthy();   // something was drawn

  await page.getByTestId('draw-stop').click();
  await expect.poll(async () => (await health(request)).pinned).toBeNull();
  expect(page.errors).toEqual([]);
});

test('animate frames, play them on the board and save a GIF', async ({ page, request }) => {
  await page.goto('/animate');
  await expect(page.getByTestId('frames')).toBeVisible();
  await stroke(page, [0.2, 0.2], [0.8, 0.2]);
  await page.keyboard.press('n');
  await stroke(page, [0.2, 0.8], [0.8, 0.8]);
  await expect(page.getByTestId('frame-1')).toBeVisible();
  await expect.poll(async () => (await sketch(request)).frames.length).toBe(2);

  await page.getByTestId('draw-name').fill('two lines');
  await page.getByTestId('draw-save').click();
  await expect(page.locator('#toast')).toContainText('drawn-two-lines');
  const gifs = await (await request.get('/api/gifs')).json();
  expect(gifs.map(g => g.id)).toContain('upload/all/drawn-two-lines.gif');
  await request.delete('/api/gifs/upload/all/drawn-two-lines.gif');
  expect(page.errors).toEqual([]);
});
