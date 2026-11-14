import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [
    frappeui({
      frontendRoute: '/life',
      frappeProxy: { port: 8080 },
      buildConfig: {
        outDir: '../lifeos/public/frontend',
        indexHtmlPath: '../lifeos/www/life.html',
        baseUrl: '/assets/lifeos/frontend/',
      },
    }),
    vue(),
  ],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  build: { chunkSizeWarningLimit: 1500 },
})
