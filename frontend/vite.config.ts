import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  base: './',
  plugins: [
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => tag === 'webview',
        },
      },
    }),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:30000',
        changeOrigin: true,
      },
      '/chat': {
        target: 'http://127.0.0.1:30000',
        changeOrigin: true,
      },
      '/system': {
        target: 'http://127.0.0.1:30000',
        changeOrigin: true,
      },
      '/uploads': {
        target: 'http://127.0.0.1:30000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:30000',
        ws: true,
      },
    },
  },
})
