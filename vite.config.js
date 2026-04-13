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
  },
});
