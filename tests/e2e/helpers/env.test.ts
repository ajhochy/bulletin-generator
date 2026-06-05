import { describe, it, expect } from 'vitest';
import { loadE2eEnv } from './env';

describe('loadE2eEnv', () => {
  it('throws a clear error when a required var is missing', () => {
    expect(() => loadE2eEnv({}, ['SUPABASE_URL'])).toThrow(/SUPABASE_URL/);
  });
  it('returns the requested vars when present', () => {
    const env = loadE2eEnv({ SUPABASE_URL: 'x', SUPABASE_ANON_KEY: 'y' }, [
      'SUPABASE_URL',
      'SUPABASE_ANON_KEY',
    ]);
    expect(env).toEqual({ SUPABASE_URL: 'x', SUPABASE_ANON_KEY: 'y' });
  });
});
