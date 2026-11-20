<template>
  <Sources v-if="KIND[current] !== undefined" :key="current" place="all" :screen="current === 'all' ? 'sources' : 'library-' + current" />
  <template v-else-if="current === 'notes'">
    <Graph v-if="route.query.view === 'graph'" />
    <Wiki v-else-if="['changes', 'health', 'rules'].includes(route.query.view)" :section="route.query.view" />
    <Library v-else />
  </template>
  <Graph v-else-if="current === 'people'" />
  <Timeline v-else-if="current === 'timeline'" />
  <Archive v-else-if="current === 'archive'" />
  <PlaceLinks :links="LINKS" label="More in the Library" />
</template>
<script setup>
// Library, one of the four places (issue 14): Everything, Notes, Documents, People and Chats. The tabs are paths
// (/library/notes); every screen open here shows them under its header (PageHead). Until each tab's own issue lands it
// shows the nearest screen: Documents and Chats are Everything held to that kind, People is the graph of people and
// what links them. The Timeline, the graph, sensitive documents and the trash and archive are linked under every tab.
import { computed, provide, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Sources from '@/pages/Sources.vue'
import Library from '@/pages/Library.vue'
import Graph from '@/pages/Graph.vue'
import Wiki from '@/pages/Wiki.vue'
import Timeline from '@/pages/Timeline.vue'
import Archive from '@/pages/Archive.vue'
import PlaceLinks from '@/components/PlaceLinks.vue'
import { LIBRARY_TABS, libraryPath } from '@/lib/nav'

const props = defineProps({ tab: String })
const route = useRoute()
const router = useRouter()
const current = computed(() => props.tab || 'all')
// the list's kind each tab holds ('' for any kind)
const KIND = { all: '', documents: 'documents', chats: 'chats' }
const LINKS = [
  { key: 'timeline', label: 'Timeline', icon: 'lucide-history', to: '/library/timeline' },
  { key: 'graph', label: 'Graph', icon: 'lucide-waypoints', to: { path: '/library/notes', query: { view: 'graph' } } },
  { key: 'sensitive', label: 'Sensitive documents', icon: 'lucide-lock', to: { path: '/library/documents', query: { sensitive: '1' } } },
  { key: 'archive', label: 'Trash and archive', icon: 'lucide-archive', to: '/library/archive' },
]
// Documents and Chats open on their kind; choosing another kind in the list moves to the tab that holds it
let settled = false
watch(() => route.query.tab, (t) => {
  const kind = KIND[current.value]
  if (!kind) return
  if (t === kind) { settled = true; return }
  if (!settled) return router.replace({ query: { ...route.query, tab: kind } })
  router.replace({ path: KIND.documents === t || KIND.chats === t ? `/library/${t}` : '/library', query: route.query })
}, { immediate: true })
// the Timeline and the archive are pages of Everything; the graph of notes is a view of Notes
const PAGES = ['timeline', 'archive']
provide('placeTabs', computed(() => ({ tabs: LIBRARY_TABS, current: PAGES.includes(current.value) ? null : current.value, label: 'Library',
  set: (v) => router.push(libraryPath(v)) })))
</script>
