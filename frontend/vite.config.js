import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],

  // Vitest transforms test files with esbuild rather than through the react
  // plugin's pipeline, so the JSX runtime has to be named here too. Without
  // it every .test.jsx fails with "React is not defined".
  esbuild: {
    jsx: 'automatic',
  },

  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    // Components only. Anything needing a running API belongs in the backend
    // smoke test, which drives the real thing rather than a mock of it.
    include: ['src/**/*.test.{js,jsx}'],
  },
});
