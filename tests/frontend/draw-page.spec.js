// End-to-end tests of the Draw and Animate pages against the real controller (fake panel).
const { test, expect } = require('@playwright/test');

const health = async (request) => (await request.get('/api/health')).json();
const sketch = async (request) => (await request.get('/api/sketch')).json();

test.beforeEach(async ({ page, request }) => {
  await request.post('/api/state', { data: { power: true, brightness: 60 } });
  await request.delete('/api/pin');
  // A blank one-frame drawing on the board, so no test picks up the last one's animation
  const [w, h] = (await sketch(request)).size;
  await request.put('/api/sketch', { data: { width: w, height: h, show: false,
    frames: [Buffer.alloc(w * h * 3).toString('base64')] } });
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

test('Animate starts from an example, and examples load as frames you can undo', async ({ page, request }) => {
  await page.goto('/animate');
  await expect(page.getByTestId('frame-9')).toBeVisible();   // the bouncing ball, 10 frames
  expect((await health(request)).pinned).toBeNull();          // not on the board until you edit
  await page.getByTestId('example-heartbeat').click();
  await expect(page.locator('#strip > *')).toHaveCount(6);
  await expect.poll(async () => (await sketch(request)).frames.length).toBe(6);
  await page.keyboard.press('Control+z');
  await expect(page.locator('#strip > *')).toHaveCount(10);
  expect(page.errors).toEqual([]);
});

test('onion skin shows the frame before (the last one on frame 1), and Show on board works with Live off', async ({ page, request }) => {
  await page.goto('/animate');
  await expect(page.getByTestId('frame-9')).toBeVisible();
  const pixels = () => page.evaluate(() => Array.from($('#canvas').getContext('2d').getImageData(0, 0, W, H).data).join());
  const withOnion = await pixels();
  await page.locator('#onion').uncheck();
  expect(await pixels()).not.toEqual(withOnion);   // frame 1 had frame 10's ghost
  await page.locator('#onion').check();
  expect(await pixels()).toEqual(withOnion);

  await page.getByTestId('draw-live').uncheck();
  await page.getByTestId('anim-show').click();
  await expect.poll(async () => (await health(request)).pinned?.scene).toBe('sketch');
  expect((await sketch(request)).frames).toHaveLength(10);
  expect(page.errors).toEqual([]);
});

test('animate frames, play them on the board and save a GIF', async ({ page, request }) => {
  await page.goto('/animate');
  await expect(page.getByTestId('frames')).toBeVisible();
  await stroke(page, [0.2, 0.2], [0.8, 0.2]);
  await page.keyboard.press('n');
  await stroke(page, [0.2, 0.8], [0.8, 0.8]);
  await expect(page.getByTestId('frame-10')).toBeVisible();   // after the example's ten
  await expect.poll(async () => (await sketch(request)).frames.length).toBe(11);

  await page.getByTestId('draw-name').fill('two lines');
  await page.getByTestId('draw-save').click();
  await expect(page.locator('#toast')).toContainText('drawn-two-lines');
  const gifs = await (await request.get('/api/gifs')).json();
  expect(gifs.map(g => g.id)).toContain('upload/all/drawn-two-lines.gif');
  await request.delete('/api/gifs/upload/all/drawn-two-lines.gif');
  expect(page.errors).toEqual([]);
});

// --- every control ------------------------------------------------------------------

const px = (page, x, y) => page.evaluate(([x, y]) => Array.from(frames[cur].slice((y * W + x) * 3, (y * W + x) * 3 + 3)), [x, y]);
async function tap(page, x, y) {   // click the middle of one cell
  const canvas = page.getByTestId('draw-canvas');
  const position = await canvas.evaluate((c, [x, y]) =>
    ({ x: (x + .5) / W * c.clientWidth, y: (y + .5) / H * c.clientHeight }), [x, y]);
  await canvas.click({ position });
}
const blur = page => page.evaluate(() => document.activeElement?.blur());

test('Draw: every tool and button does its job', async ({ page, request }) => {
  await page.goto('/draw');
  await expect(page.getByTestId('draw-status')).not.toBeEmpty();
  const W = await page.evaluate(() => W);
  const BLUE = [41, 173, 255], YELLOW = [255, 236, 39], BLACK = [0, 0, 0];

  await page.getByRole('button', { name: '#29adff' }).click();                 // palette
  expect(await page.evaluate(() => color)).toEqual(BLUE);
  await expect(page.getByRole('button', { name: '#29adff' })).toHaveClass(/on/);
  await tap(page, 2, 2);                                                         // pen
  expect(await px(page, 2, 2)).toEqual(BLUE);
  await expect.poll(async () => {                                                // live: on the board
    const f = Buffer.from((await sketch(request)).frames[0], 'base64');
    return Array.from(f.subarray((2 * W + 2) * 3, (2 * W + 2) * 3 + 3));
  }).toEqual(BLUE);

  await page.getByTestId('size').selectOption('3');                              // brush size
  await tap(page, 10, 10);
  expect(await px(page, 9, 9)).toEqual(BLUE);
  expect(await px(page, 11, 11)).toEqual(BLUE);
  expect(await px(page, 12, 12)).toEqual(BLACK);
  await page.getByTestId('size').selectOption('1');

  await page.getByTestId('mirror').check();                                      // mirror
  await tap(page, 3, 20);
  expect(await px(page, W - 4, 20)).toEqual(BLUE);
  await page.getByTestId('mirror').uncheck();

  await page.getByTestId('opacity').fill('50');                                  // opacity over black
  await expect(page.locator('#alphav')).toHaveText('50%');
  await tap(page, 20, 5);
  expect(await px(page, 20, 5)).toEqual([21, 87, 128]);
  await page.getByTestId('opacity').fill('100');

  await page.getByTestId('tool-picker').click();                                 // picker
  await tap(page, 20, 5);
  expect(await page.evaluate(() => color)).toEqual([21, 87, 128]);
  expect(await page.evaluate(() => tool)).toBe('pen');                           // and back to the pen

  await page.getByRole('button', { name: '#ffec27' }).click();
  await page.getByTestId('tool-fill').click();                                   // fill
  await tap(page, 30, 30);
  expect(await px(page, 30, 30)).toEqual(YELLOW);
  expect(await px(page, 2, 2)).toEqual(BLUE);                                    // stops at other colors

  await page.getByTestId('tool-eraser').click();                                 // eraser
  await tap(page, 2, 2);
  expect(await px(page, 2, 2)).toEqual(BLACK);
  await page.getByTestId('undo').click();                                        // undo, redo
  expect(await px(page, 2, 2)).toEqual(BLUE);
  await page.getByTestId('redo').click();
  expect(await px(page, 2, 2)).toEqual(BLACK);

  await page.getByTestId('draw-color').fill('#00e436');                          // color input
  expect(await page.evaluate(() => color)).toEqual([0, 228, 54]);
  expect(await page.evaluate(() => tool)).toBe('pen');                           // picking a color leaves the eraser

  await blur(page);                                                              // keyboard
  for (const [key, t] of [['e', 'eraser'], ['f', 'fill'], ['i', 'picker'], ['b', 'pen']]) {
    await page.keyboard.press(key);
    expect(await page.evaluate(() => tool)).toBe(t);
  }
  await page.keyboard.press('Control+z');
  expect(await px(page, 2, 2)).toEqual(BLUE);

  await page.getByTestId('grid').uncheck();                                      // grid
  await expect(page.locator('#wrap')).not.toHaveClass(/grid/);
  await page.getByTestId('grid').check();
  await expect(page.locator('#wrap')).toHaveClass(/grid/);

  await page.getByTestId('draw-clear').click();                                  // clear
  expect(await page.evaluate(() => frames[cur].some(v => v))).toBe(false);

  await expect.poll(async () => (await sketch(request)).frames[0]).toEqual(      // wait for the clear to land
    await page.evaluate(() => b64(Uint8Array.from(frames[cur]))));
  await page.getByTestId('draw-live').uncheck();                                 // live off: the board keeps the old one
  const before = (await sketch(request)).frames[0];
  await tap(page, 5, 5);
  await page.waitForTimeout(300);
  expect((await sketch(request)).frames[0]).toEqual(before);
  await page.getByTestId('draw-live').check();                                   // and on again sends it
  await expect.poll(async () => (await sketch(request)).frames[0]).not.toEqual(before);
  expect(page.errors).toEqual([]);
});

test('Animate: frame buttons and keys step, add, copy, delete, move, change speed and play', async ({ page }) => {
  await page.goto('/animate');
  const at = () => page.evaluate(() => cur);
  const count = () => page.evaluate(() => frames.length);
  const frameData = i => page.evaluate(i => Array.from(frames[i]).join(), i);
  await expect(page.getByTestId('frame-pos')).toHaveText('1 / 10');

  await page.getByTestId('frame-next').click();                                  // ◀ ▶ step, and wrap
  expect(await at()).toBe(1);
  await expect(page.getByTestId('frame-pos')).toHaveText('2 / 10');
  await page.getByTestId('frame-prev').click();
  await page.getByTestId('frame-prev').click();
  expect(await at()).toBe(9);
  await blur(page);
  await page.keyboard.press('ArrowRight');                                       // arrow keys
  expect(await at()).toBe(0);
  await page.keyboard.press('ArrowLeft');
  expect(await at()).toBe(9);
  await page.keyboard.press('.');
  expect(await at()).toBe(0);
  await page.keyboard.press(',');
  expect(await at()).toBe(9);
  await expect(page.getByTestId('frame-later')).toBeDisabled();                  // can't move past the end

  const last = await frameData(9);                                               // move earlier / later
  await page.getByTestId('frame-earlier').click();
  expect([await at(), await frameData(8)]).toEqual([8, last]);
  await page.getByTestId('frame-later').click();
  expect([await at(), await frameData(9)]).toEqual([9, last]);
  await blur(page);
  await page.keyboard.press('Shift+ArrowLeft');
  expect([await at(), await frameData(8)]).toEqual([8, last]);
  await page.keyboard.press('Shift+ArrowRight');
  expect([await at(), await frameData(9)]).toEqual([9, last]);
  await page.getByTestId('frame-0').click();                                     // strip thumbnails select
  expect(await at()).toBe(0);
  await expect(page.getByTestId('frame-earlier')).toBeDisabled();

  await page.getByTestId('frame-add').click();                                   // new: blank, after this one
  expect([await count(), await at()]).toEqual([11, 1]);
  expect(await page.evaluate(() => frames[1].some(v => v))).toBe(false);
  await page.getByTestId('frame-dup').click();                                   // duplicate
  expect([await count(), await at()]).toEqual([12, 2]);
  expect(await frameData(2)).toEqual(await frameData(1));
  await page.getByTestId('frame-del').click();                                   // delete
  await page.getByTestId('frame-del').click();
  expect(await count()).toBe(10);
  await blur(page);
  await page.keyboard.press('n');
  await page.keyboard.press('d');
  expect(await count()).toBe(12);
  await page.getByTestId('undo').click();
  await page.getByTestId('undo').click();
  expect(await count()).toBe(10);

  await page.getByTestId('fps').fill('20');                                      // speed
  await expect(page.locator('#fpsv')).toHaveText('20 fps');
  expect(await page.evaluate(() => ms)).toBe(50);

  const canvas = () => page.evaluate(() => $('#canvas').toDataURL());           // play / stop
  const still = await canvas();
  await page.getByTestId('anim-play').click();
  await expect(page.getByTestId('anim-play')).toHaveText('■ Stop');
  await expect.poll(canvas).not.toEqual(still);
  await blur(page);
  await page.keyboard.press(' ');
  await expect(page.getByTestId('anim-play')).toHaveText('▶ Play');
  expect(page.errors).toEqual([]);
});
