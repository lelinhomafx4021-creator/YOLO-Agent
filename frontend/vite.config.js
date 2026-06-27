import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8009',
      '/images': 'http://127.0.0.1:8009',
      '/runs': 'http://127.0.0.1:8009',
      '/exports': 'http://127.0.0.1:8009',
      '/model_registry': 'http://127.0.0.1:8009',
      '/inferences': 'http://127.0.0.1:8009',
    },
  },
})
