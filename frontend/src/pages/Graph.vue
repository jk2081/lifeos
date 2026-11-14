<template>
  <PageHead title="Graph" :sub="d ? `${d.nodes.length} records · ${d.edges.length} links${center ? ' · two steps around one record' : ''}` : ''">
    <button v-if="center" class="bt s" type="button" @click="setCenter('')">Show the whole space</button>
  </PageHead>
  <div class="bd" style="flex: 1">
    <div class="chips">
      <span v-for="t in LEGEND" :key="t.type" class="lgd"><i :style="`background: var(${t.color})`"></i>{{ t.label }}</span>
      <span class="lgd"><i style="background: var(--mut)"></i>Task, chat or project that is linked</span>
      <span style="flex: 1"></span>
      <span v-if="picked" class="chips">
        <b style="font-weight: 500">{{ picked.label }}</b>
        <RouterLink class="bt s" :to="picked.route">Open</RouterLink>
        <button class="bt s" type="button" @click="setCenter(picked.id)">Two steps around it</button>
      </span>
      <span v-else class="mt">Click a record to select it. Double-click to open it.</span>
    </div>
    <div v-show="d && d.nodes.length" ref="host" class="cy" role="img" aria-label="Graph of linked records"></div>
    <div v-if="d && !d.nodes.length" class="cd"><Empty title="Nothing to draw yet."
      hint="Notes, people, goals and vault documents show here, joined by [[links]], parent notes and fields such as a document's holder." /></div>
    <details v-if="d && d.edges.length" class="mt"><summary>The same links as a list</summary>
      <ul style="margin: 8px 0 0; padding-left: 18px; list-style: disc"><li v-for="(e, i) in d.edges.slice(0, 200)" :key="i">{{ label(e.source) }} → {{ label(e.target) }} <span>({{ e.kind }})</span></li></ul></details>
  </div>
</template>
<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import cytoscape from 'cytoscape'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'

const LEGEND = [{ type: 'Note', label: 'Note', color: '--series-1' }, { type: 'Person', label: 'Person', color: '--series-2' },
  { type: 'Goal', label: 'Goal', color: '--series-3' }, { type: 'Document', label: 'Vault document', color: '--series-4' }]
const route = useRoute()
const router = useRouter()
const host = ref(null)
const d = ref(null)
const picked = ref(null)
const center = ref(route.query.center || '')
let cy = null
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
const label = (id) => d.value.nodes.find((n) => n.id === id)?.label || id

function draw() {
  if (cy) cy.destroy()
  const color = Object.fromEntries(LEGEND.map((t) => [t.type, css(t.color)]))
  cy = cytoscape({
    container: host.value,
    elements: [
      ...d.value.nodes.map((n) => ({ data: { id: n.id, label: n.label, color: color[n.type] || css('--mut'), route: n.route, full: n.label } })),
      ...d.value.edges.map((e, i) => ({ data: { id: 'e' + i, source: e.source, target: e.target, kind: e.kind } })),
    ],
    style: [
      { selector: 'node', style: { 'background-color': 'data(color)', label: 'data(label)', color: css('--ink'), 'font-size': 11, 'font-family': 'Inter, system-ui, sans-serif',
        'text-valign': 'bottom', 'text-margin-y': 5, 'text-wrap': 'ellipsis', 'text-max-width': 120, width: 16, height: 16, 'border-width': 2, 'border-color': css('--bg'), 'text-background-color': css('--bg'), 'text-background-opacity': 0.8, 'text-background-padding': 2 } },
      { selector: 'node:selected', style: { 'border-color': css('--ink'), width: 20, height: 20 } },
      { selector: 'edge', style: { width: 1.5, 'line-color': css('--line4'), 'target-arrow-color': css('--line4'), 'target-arrow-shape': 'triangle', 'arrow-scale': 0.8, 'curve-style': 'bezier' } },
      { selector: 'edge[kind = "parent"]', style: { 'line-style': 'dashed' } },
    ],
    layout: { name: 'preset' },
    minZoom: 0.3, maxZoom: 2.5, wheelSensitivity: 0.3,
  })
  // Linked records are laid out by force; records with no link yet sit in rows underneath, so labels never pile up.
  const w = host.value.clientWidth, h = host.value.clientHeight
  const linked = cy.nodes().filter((n) => n.degree() > 0)
  const alone = cy.nodes().filter((n) => n.degree() === 0)
  const rows = Math.ceil(alone.length / Math.max(1, Math.floor(w / 150)))
  const top = alone.length ? Math.max(h * 0.45, h - rows * 60 - 40) : h
  if (linked.length) linked.union(cy.edges()).layout({ name: 'cose', animate: false, fit: false, padding: 30, nodeRepulsion: 9000, idealEdgeLength: 90, componentSpacing: 80,
    nodeDimensionsIncludeLabels: true, boundingBox: { x1: 0, y1: 0, w, h: linked.length ? top - 20 : 0 } }).run()
  if (alone.length) alone.layout({ name: 'grid', fit: false, avoidOverlap: true, cols: Math.max(1, Math.floor(w / 150)), boundingBox: { x1: 20, y1: linked.length ? top : 20, w: w - 40, h: rows * 60 } }).run()
  cy.fit(undefined, 30)
  if (cy.zoom() > 1) { cy.zoom(1); cy.center() }
  cy.on('tap', 'node', (evt) => { const n = evt.target.data(); picked.value = { id: n.id, label: n.full, route: n.route } })
  cy.on('tap', (evt) => { if (evt.target === cy) picked.value = null })
  cy.on('dbltap', 'node', (evt) => router.push(evt.target.data('route')))
}
async function load() {
  const res = await tryCall(() => api('graph.get', { space: store.space, center: center.value || undefined }))
  if (!res) return
  d.value = res
  picked.value = null
  if (res.nodes.length) requestAnimationFrame(draw)
}
function setCenter(id) {
  center.value = id
  router.replace({ query: id ? { center: id } : {} })
  load()
}
onMounted(load)
onBeforeUnmount(() => cy && cy.destroy())
</script>
<style scoped>
.cy { flex: 1; min-height: 520px; border: 1px solid var(--line); border-radius: 10px; background: var(--soft); }
.lgd { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--mut2); }
.lgd i { width: 10px; height: 10px; border-radius: 5px; display: inline-block; }
@media (max-width: 800px) { .cy { min-height: 60vh; } }
</style>
