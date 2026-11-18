// Browser tests for the control page. Run: cd tests/frontend && npm install && npx playwright test
// PYTHON must point at an interpreter with Flask, Pillow and numpy.
const { defineConfig } = require('@playwright/test');
const base = `http://127.0.0.1:${process.env.PORT || 18765}`;   // PORT lets two checkouts test at once

module.exports = defineConfig({
  testDir: '.',
  timeout: 120_000,
  workers: 1,               // one shared board: tests run in order
  reporter: [['list']],
  use: { baseURL: base, viewport: { width: 1100, height: 900 } },
  webServer: { command: './server.sh', url: `${base}/api/health`, timeout: 60_000 },
});
