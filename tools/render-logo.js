// Renders tools/logo.html to docs/images/logo-dark.png and logo-light.png (transparent).
//   cd tests/frontend && NODE_PATH=$PWD/node_modules node ../../tools/render-logo.js
const path = require('path');
const { chromium } = require('@playwright/test');
(async () => {
  const root = path.resolve(__dirname, '..');
  const b = await chromium.launch();
  const p = await b.newPage({ deviceScaleFactor: 1 });
  for (const mode of ['dark', 'light']) {
    await p.goto('file://' + path.join(root, 'tools', 'logo.html'));
    await p.evaluate((m) => document.body.classList.add(m), mode);
    await p.evaluate(() => document.fonts.ready);
    await p.locator('.logo').screenshot({ path: path.join(root, 'docs', 'images', `logo-${mode}.png`), omitBackground: true });
  }
  await b.close();
})();
