import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// The Vue SPA. In dev, API/asset routes proxy to the running Phoenix
// dashboard (uvicorn on :7002). In prod, `vite build` emits to dist/ and
// FastAPI serves it from the `/` route.
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:7002',
      '/static': 'http://localhost:7002',
      '/data': 'http://localhost:7002',
      '/display': 'http://localhost:7002',
      '/ws': { target: 'http://localhost:7002', ws: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
