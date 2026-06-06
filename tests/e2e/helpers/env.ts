import { config as loadDotenv } from 'dotenv';

let loaded = false;
function ensureDotenv() {
  if (!loaded) {
    loadDotenv({ path: '.env.e2e' });
    loaded = true;
  }
}

export function loadE2eEnv<K extends string>(
  source: Record<string, string | undefined>,
  required: readonly K[],
): Record<K, string> {
  const out = {} as Record<K, string>;
  const missing: string[] = [];
  for (const key of required) {
    const val = source[key];
    if (!val) missing.push(key);
    else out[key] = val;
  }
  if (missing.length) {
    throw new Error(`Missing required E2E env var(s): ${missing.join(', ')}`);
  }
  return out;
}

export function e2eEnv<K extends string>(required: readonly K[]): Record<K, string> {
  ensureDotenv();
  return loadE2eEnv(process.env, required);
}
