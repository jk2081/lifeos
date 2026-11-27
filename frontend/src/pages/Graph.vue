<template>
  <PageHead :path="[{ label: 'Library', to: '/library' }]" :title="route.query.collection === 'Wiki' ? 'Wiki' : 'Notes'" :sub="d ? `Graph: ${d.nodes.length} records · ${d.edges.length} links${center ? ' · two steps around one record' : ''}` : ''">
    <TabButtons model-value="graph" :options="route.query.collection === 'Wiki' ? WIKI_VIEWS : NOTES_VIEWS" data-library-views />
    <Button v-if="center" label="Show the whole space" @click="setCenter('')" />
  </PageHead>
  <div class="page-body flex-1">
    <div class="chips">
      <span v-for="t in LEGEND" :key="t.type" class="inline-flex items-center gap-1.5 text-sm text-ink-gray-7"><span class="inline-block size-2.5 rounded-full" :style="`background: var(${t.color})`" />{{ t.label }}</span>
      <span class="inline-flex items-center gap-1.5 text-sm text-ink-gray-7"><span class="inline-block size-2.5 rounded-full" style="background: var(--ink-gray-6)" />Task or chat that is linked</span>
      <span class="flex-1" />
      <span v-if="picked" class="chips">
        <b class="text-base-medium text-ink-gray-9">{{ picked.label }}</b>
        <Button label="Open" :route="picked.route" />
        <Button label="Two steps around it" @click="setCenter(picked.id)" />
      </span>
      <span v-else class="text-sm text-ink-gray-6">Click a record to select it. Double-click to open it.</span>
    </div>
    <div v-show="d && d.nodes.length" ref="host" class="min-h-[520px] flex-1 rounded-5 border border-outline-gray-1 bg-surface-gray-1 max-md:min-h-[60vh]" role="img" aria-label="Graph of linked records" />
    <Card v-if="d && !d.nodes.length"><EmptyState line="Nothing to draw yet. Notes, people, goals and vault documents show here, joined by [[links]], parent notes and fields such as a document's holder." /></Card>
    <details v-if="d && d.edges.length" class="text-sm text-ink-gray-6"><summary class="cursor-pointer">The same links as a list</summary>
      <ul class="mt-2 list-disc pl-5"><li v-for="(e, i) in d.edges.slice(0, 200)" :key="i">{{ label(e.source) }} → {{ label(e.target) }} <span>({{ e.kind }})</span></li></ul></details>
  </div>
</template>
<script setup>
import { libraryData } from '@/data/library'
import { tokenColor } from '@/lib/tokens'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import cytoscape from 'cytoscape'
import { Button, TabButtons } from 'frappe-ui'
import { NOTES_VIEWS } from '@/lib/nav'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { tryCall } from '@/lib/api'
import { store } from '@/lib/store'

const LEGEND = [{ type: 'Note', label: 'Note', color: '--ink-blue-7' }, { type: 'Person', label: 'Person', color: '--ink-amber-7' },
  { type: 'Goal', label: 'Goal', color: '--ink-violet-6' }, { type: 'Document', label: 'Vault document', color: '--ink-green-7' }]
const route = useRoute()
const WIKI_VIEWS = [{ label: 'List', value: 'list', route: { path: '/library/notes', query: { by: 'assistant' } } }, { label: 'Graph', value: 'graph', route: { path: '/library/notes', query: { by: 'assistant', view: 'graph', collection: 'Wiki' } } }]
const router = useRouter()
const host = ref(null)
const d = ref(null)
const picked = ref(null)
const center = ref(route.query.center || '')
let cy = null
const css = tokenColor
const label = (id) => d.value.nodes.find((n) => n.id === id)?.label || id

function draw() {
  if (cy) cy.destroy()
  const color = Object.fromEntries(LEGEND.map((t) => [t.type, css(t.color)]))
  cy = cytoscape({
    container: host.value,
    elements: [
      ...d.value.nodes.map((n) => ({ data: { id: n.id, label: n.label, color: color[n.type] || css('--ink-gray-6'), route: n.route, full: n.label } })),
      ...d.value.edges.map((e, i) => ({ data: { id: 'e' + i, source: e.source, target: e.target, kind: e.kind } })),
    ],
    style: [
      { selector: 'node', style: { 'background-color': 'data(color)', label: 'data(label)', color: css('--ink-gray-9'), 'font-size': 11, 'font-family': 'Inter, system-ui, sans-serif',
        'text-valign': 'bottom', 'text-margin-y': 5, 'text-wrap': 'ellipsis', 'text-max-width': 120, width: 16, height: 16, 'border-width': 2, 'border-color': css('--surface-base'), 'text-background-color': css('--surface-base'), 'text-background-opacity': 0.8, 'text-background-padding': 2 } },
      { selector: 'node:selected', style: { 'border-color': css('--ink-gray-9'), width: 20, height: 20 } },
      { selector: 'edge', style: { width: 1.5, 'line-color': css('--ink-gray-4'), 'target-arrow-color': css('--ink-gray-4'), 'target-arrow-shape': 'triangle', 'arrow-scale': 0.8, 'curve-style': 'bezier' } },
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
  const res = await tryCall(() => libraryData.graph.get({ space: store.space, center: center.value || undefined, collection: route.query.collection || undefined, area: store.lensArea || undefined }))
  if (!res) return
  d.value = res
  picked.value = null
  if (res.nodes.length) requestAnimationFrame(draw)
}
function setCenter(id) {
  center.value = id
  router.replace({ query: { ...(id ? { center: id } : {}), ...(route.query.collection ? { collection: route.query.collection } : {}) } })
  load()
}
onMounted(load)
onBeforeUnmount(() => cy && cy.destroy())
</script>
