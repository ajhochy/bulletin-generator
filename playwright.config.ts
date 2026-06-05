import { defineConfig, devices } from '@playwright/test';
import { config as loadDotenv } from 'dotenv';

loadDotenv({ path: '.env.e2e' });

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8080';

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'python3 server.py',
    url: `${BASE_URL}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      APP_MODE: 'server',
      DATABASE_URL: process.env.DATABASE_URL ?? '',
      SUPABASE_URL: process.env.SUPABASE_URL ?? '',
      SUPABASE_ANON_KEY: process.env.SUPABASE_ANON_KEY ?? '',
      SUPABASE_JWT_SECRET: process.env.SUPABASE_JWT_SECRET ?? '',
    },
  },
  projects: [
    { name: 'core-setup', testMatch: /helpers\/auth\.setup\.ts/, grep: /@core-setup/, teardown: 'core-teardown' },
    { name: 'core-teardown', testMatch: /helpers\/auth\.teardown\.ts/ },
    { name: 'live-setup', testMatch: /helpers\/auth\.setup\.ts/, grep: /@live-setup/ },
    {
      name: 'core',
      grep: /@core/,
      dependencies: ['core-setup'],
      use: { ...devices['Desktop Chrome'], storageState: 'tests/e2e/.auth/core.json' },
    },
    {
      name: 'live',
      grep: /@live/,
      dependencies: ['live-setup'],
      use: { ...devices['Desktop Chrome'], storageState: 'tests/e2e/.auth/live.json' },
    },
  ],
});
