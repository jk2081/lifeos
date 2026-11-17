<template>
  <Sources v-if="current === 'all' || current === 'captures'" :key="current" :place="current" />
  <template v-else-if="current === 'notes'">
    <Graph v-if="route.query.view === 'graph'" />
    <Wiki v-else-if="route.query.by === 'assistant'" />
    <Library v-else />
  </template>
  <Timeline v-else-if="current === 'timeline'" />
  <Archive v-else-if="current === 'archive'" />
</template>
<script setup>
// Library, one of the four places (UX fixes, set 6): All, Notes, Captures, Timeline and Archive. The tabs are paths
// (/library/notes); every screen open here shows them under its header (PageHead).
import { computed, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Sources from '@/pages/Sources.vue'
import Library from '@/pages/Library.vue'
import Graph from '@/pages/Graph.vue'
import Wiki from '@/pages/Wiki.vue'
import Timeline from '@/pages/Timeline.vue'
import Archive from '@/pages/Archive.vue'
import { LIBRARY_TABS, libraryPath } from '@/lib/nav'

const props = defineProps({ tab: String })
const route = useRoute()
const router = useRouter()
const current = computed(() => props.tab || 'all')
provide('placeTabs', computed(() => ({ tabs: LIBRARY_TABS, current: current.value, label: 'Library', set: (v) => router.push(libraryPath(v)) })))
</script>
