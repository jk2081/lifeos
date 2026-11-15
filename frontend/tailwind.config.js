import frappeUIPreset, { content } from 'frappe-ui/tailwind'

export default {
  presets: [frappeUIPreset],
  content: [
    ...content,
    // @framework/ui ships raw source; its classes and lucide icon names are scanned through the link in node_modules
    './node_modules/@framework/ui/src/**/*.{vue,ts}',
    '!./node_modules/@framework/ui/src/**/{stories,tests}/**',
    './index.html',
    './src/**/*.{vue,js}',
  ],
  theme: { extend: {} },
  plugins: [],
}
