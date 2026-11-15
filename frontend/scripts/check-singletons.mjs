// Builds the front end in memory and checks that vue, vue-router, frappe-ui and reka-ui are each bundled from one place.
// Run inside the bench container:  cd apps/lifeos/frontend && node scripts/check-singletons.mjs
import { build } from 'vite'

const roots = {}
await build({
  logLevel: 'silent',
  build: { write: false },
  plugins: [{
    name: 'singletons',
    generateBundle() {
      for (const id of this.getModuleIds()) {
        const m = /^(.*\/node_modules\/(vue|vue-router|frappe-ui|reka-ui|@vue\/runtime-core))\//.exec(id.replace(/^\0/, ''))
        if (m) (roots[m[2]] ||= new Set()).add(m[1])
      }
    },
  }],
})
let bad = false
for (const name of ['vue', '@vue/runtime-core', 'vue-router', 'frappe-ui', 'reka-ui']) {
  const set = [...(roots[name] || [])]
  console.log(`${set.length === 1 ? 'ok  ' : 'FAIL'} ${name}: ${set.join(', ') || 'not bundled'}`)
  if (set.length !== 1) bad = true
}
process.exit(bad ? 1 : 0)
