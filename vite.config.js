import { cpSync, existsSync } from 'node:fs';
import path from 'node:path';
import { defineConfig } from 'vite';

function copyLegacyScriptsPlugin() {
  return {
    name: 'copy-legacy-scripts',
    closeBundle() {
      const rootDir = process.cwd();
      const srcDir = path.join(rootDir, 'src', 'js');
      const outDir = path.join(rootDir, 'dist', 'src', 'js');

      if (!existsSync(srcDir)) return;
      cpSync(srcDir, outDir, { recursive: true });
    },
  };
}

export default defineConfig({
  plugins: [copyLegacyScriptsPlugin()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.js'],
    // Never scan agent worktrees or deps — they hold stale duplicate specs
    // that inflate counts and can false-fail if the copies diverge from HEAD.
    exclude: ['**/node_modules/**', '**/.claude/**', '**/dist/**', 'tests/e2e/**/*.spec.ts'],
  },
});
