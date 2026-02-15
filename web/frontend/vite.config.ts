import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      workbox: {
        // Cache JS/CSS/font chunks and images
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
        // Don't precache source maps
        globIgnores: ['**/*.map'],
        runtimeCaching: [
          {
            // Cache Google Fonts
            urlPattern: /^https:\/\/fonts\.(googleapis|gstatic)\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts',
              expiration: { maxEntries: 30, maxAgeSeconds: 60 * 60 * 24 * 365 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // Cache map tiles
            urlPattern: /^https:\/\/.*tile.*\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'map-tiles',
              expiration: { maxEntries: 500, maxAgeSeconds: 60 * 60 * 24 * 30 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
      manifest: {
        name: 'Remnawave Admin',
        short_name: 'Remnawave',
        description: 'VPN Infrastructure Admin Panel',
        theme_color: '#0d1117',
        background_color: '#0d1117',
        display: 'standalone',
        icons: [
          {
            src: '/favicon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
          },
        ],
      },
    }),
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
