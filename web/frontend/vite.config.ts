import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    host: true,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8081',
        changeOrigin: true,
      },
      '/ws': {
        target: process.env.VITE_WS_URL || 'ws://localhost:8081',
        ws: true,
      },
    },
  },
  preview: {
    port: 4173,
    host: true,
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          // Let Vite handle CSS association with its importing chunk naturally;
          // forcing CSS into a manualChunk breaks lazy-load CSS code-splitting.
          if (id.endsWith('.css')) return

          // Core React runtime — cached long-term
          if (
            id.includes('/react/') ||
            id.includes('/react-dom/') ||
            id.includes('/react-router') ||
            id.includes('/use-sync-external-store/') ||
            id.includes('/scheduler/')
          ) {
            return 'vendor-react'
          }

          // Data layer (state, HTTP, queries)
          if (
            id.includes('/zustand/') ||
            id.includes('/axios/') ||
            id.includes('/@tanstack/react-query/')
          ) {
            return 'vendor-data'
          }

          // i18n
          if (
            id.includes('/i18next/') ||
            id.includes('/react-i18next/') ||
            id.includes('/i18next-browser-languagedetector/')
          ) {
            return 'vendor-i18n'
          }

          // UI primitives (Radix)
          if (id.includes('/@radix-ui/')) {
            return 'vendor-radix'
          }

          // Charts
          if (id.includes('/recharts/') || id.includes('/d3-')) {
            return 'vendor-charts'
          }

          // Maps (heavy — loaded only with Analytics page)
          if (id.includes('/leaflet/') || id.includes('/react-leaflet/')) {
            return 'vendor-maps'
          }

          // Icons
          if (id.includes('/lucide-react/')) {
            return 'vendor-icons'
          }
        },
      },
    },
  },
})
