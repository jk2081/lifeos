import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import frameworkUI from '@framework/ui/vite'
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
    // @framework/ui is raw source linked from apps/frappe/ui; this keeps one copy of vue, vue-router, frappe-ui and reka-ui
    frameworkUI(),
    vue(),
  ],
  // '@fui' is frappe-ui's own data layer (docStore, idbStore), which the package does not export; one file on disk, so one copy in the bundle
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src'), '@fui': path.resolve(import.meta.dirname, 'node_modules/frappe-ui/src/data-fetching') } },
  build: { chunkSizeWarningLimit: 1500 },
})
