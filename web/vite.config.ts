import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base './' makes the build work from any GitHub Pages sub-path.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      // MapLibre is large and changes rarely, so it gets its own long-lived cached file.
      output: { manualChunks: { maplibre: ['maplibre-gl'] } },
    },
  },
});
