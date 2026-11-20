import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// /api ile başlayan istekler backend'e yönlendirilir; böylece CORS derdi olmaz.
// Docker'da backend adresi "http://backend:8000", yerelde "http://localhost:8000".
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // Docker + Windows'ta dosya değişikliklerinin algılanması için
    watch: { usePolling: true },
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
})
