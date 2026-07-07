import { defineConfig, devices } from '@playwright/test'

// Smoke tests drive the running dev stack. `reuseExistingServer` means if the
// backend (:7002) and vite (:5173) are already up, we use them; otherwise
// Playwright starts them. The backend needs the Phoenix env + config.
export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'uv run --directory .. phoenix dashboard',
      url: 'http://localhost:7002/healthz',
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: 'bun run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
})
