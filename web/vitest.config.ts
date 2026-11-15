import { defineConfig } from 'vitest/config'

// Separate from vite.config.ts on purpose: these are pure-TypeScript unit tests (calendar parsing, the
// on-device analysis) that need none of the app's React/Tailwind plugins.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
