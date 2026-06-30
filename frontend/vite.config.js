import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('/@vue-flow/')) return 'flow'
          if (id.includes('/naive-ui/')) return 'naive'
          if (id.includes('/vue/') || id.includes('/pinia/')) return 'vue'
          return 'vendor'
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        bypass(req) {
          if (req.url?.startsWith('/api-analysis')) {
            return '/index.html'
          }
        }
      }
    }
  }
})
