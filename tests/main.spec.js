import { describe, expect, it } from 'vitest';
import { LEGACY_SCRIPT_PATHS } from '../src/js/main.js';

describe('legacy compatibility loader', () => {
  it('preserves the existing startup order', () => {
    expect(LEGACY_SCRIPT_PATHS[0]).toBe('/src/js/state.js');
    expect(LEGACY_SCRIPT_PATHS.at(-1)).toBe('/src/js/app.js');
    expect(LEGACY_SCRIPT_PATHS).toContain('/src/js/preview.js');
    expect(LEGACY_SCRIPT_PATHS.indexOf('/src/js/state.js')).toBeLessThan(
      LEGACY_SCRIPT_PATHS.indexOf('/src/js/app.js')
    );
  });
});
