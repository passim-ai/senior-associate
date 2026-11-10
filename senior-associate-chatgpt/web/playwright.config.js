import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir: './tests', testMatch: '**/*.spec.js', workers: 1, timeout: 45000,
  use: {baseURL: 'http://127.0.0.1:4178', channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome', viewport: {width: 1140, height: 950}},
  outputDir: '../artifacts/browser-results',
  webServer: {command: 'uv run --locked --script ../tests/browser_host.py', url: 'http://127.0.0.1:4178', reuseExistingServer: false, timeout: 30000},
});
