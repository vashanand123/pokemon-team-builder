import { defineConfig, devices } from '@playwright/test'

// Spins up the backend (on a throwaway e2e DB) and the Vite dev server, then runs
// the browser tests against the dev server (which proxies /api + /healthz to :8000).
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false,
  use: { baseURL: 'http://localhost:5173' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'uv run python -m uvicorn app.main:app --port 8000',
      cwd: '../backend',
      url: 'http://localhost:8000/healthz',
      reuseExistingServer: false,
      timeout: 120_000,
      env: { DATABASE_URL: 'sqlite+aiosqlite:///./e2e.db' },
    },
    {
      command: 'npm run dev -- --port 5173',
      url: 'http://localhost:5173',
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
