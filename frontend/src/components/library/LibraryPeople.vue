<template>
  <ListView ref="list" title="Library" sub="Every person and organisation, with everything Life OS knows about them." noun="people and organisations" screen="library-people" doctype="Life Person" mode="feed"
    :spec="SPEC" :quick="['kind']" :only="['kind']" :sortable="false" :groupable="false" :watch-keys="['q']" :fetch="fetch" :row-ref="(r) => `person:${r.name}`" :row-key="(r) => r.name"
    :row-label="(r) => r.title" empty-title="No people or organisations yet." empty-hint="People and organisations you capture, or the Brain finds in what you keep, will show up here."
    :empty-action="writable ? { label: 'Chat', icon: 'lucide-message-square', click: () => openChat() } : null" @loaded="loaded = true">
    <template #above>
      <div class="flex flex-wrap items-center gap-2" data-library-people :data-loaded="loaded ? 1 : 0" data-people-filters>
        <TextInput v-model="q" class="w-full min-w-0 sm:w-80" type="search" placeholder="Search people and organisations..." aria-label="Search people and organisations" data-people-search @keydown.enter="applyQuery" />
      </div>
    </template>
    <template #row="{ row: r }">
      <div class="flex min-w-0 flex-col gap-1 md:grid md:grid-cols-[2rem_minmax(0,1fr)_minmax(0,9rem)_minmax(0,16rem)] md:items-center md:gap-4" data-people-row :data-name="r.name" :data-kind="r.kind">
        <div class="flex min-w-0 items-start gap-3 md:contents">
          <span class="flex size-8 flex-none items-center justify-center rounded-md text-sm-medium" :class="r.letter === 'O' ? 'bg-surface-amber-2 text-ink-gray-9' : 'bg-surface-blue-2 text-ink-gray-9'" aria-hidden="true" data-people-letter>{{ r.letter }}</span>
          <div class="min-w-0 flex-1">
            <div class="break-words text-base-medium text-ink-gray-9" data-people-title>{{ r.title }}<Badge class="ml-2" size="sm" :label="r.kind" /></div>
            <div class="break-words text-sm text-ink-gray-6" data-people-line>{{ r.line || (r.kind === 'Organisation' ? 'Organisation' : 'Person') }}<span v-if="r.kind === 'Organisation' && r.people_count"> · {{ r.people_count }} {{ r.people_count === 1 ? 'person' : 'people' }}</span></div>
          </div>
        </div>
        <div class="min-w-0 truncate pl-11 text-sm text-ink-gray-7 md:pl-0 md:text-base" data-people-area-name>{{ r.area_name }}</div>
        <div class="min-w-0 truncate pl-11 text-sm text-ink-gray-6 md:pl-0" data-people-last>
          <template v-if="r.last">{{ short(r.last.date) }} · {{ r.last.title }}</template><template v-else>Not mentioned yet</template>
        </div>
      </div>
    </template>
  </ListView>
</template>
<script setup>
import { openChat } from '@/lib/ask'
// Library > People (issue 25): one row per person or organisation with its kind, a line about them, area and the newest thing that mentions them. The shared list
// (ListView): the area is the lens, Kind a filter of the shared bar, both in the address (kind, area) as on every list; the search box reads names, other names and roles (q).
// A row opens the person's page.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, TextInput } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import { tryCall } from '@/lib/api'
import { libraryData } from '@/data/library'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'

const route = useRoute()
const router = useRouter()
const SPEC = [{ key: 'area', field: 'area', kind: 'link' }, { key: 'kind', field: 'kind', kind: 'value' }]
const q = ref(route.query.q || '')
const loaded = ref(false)
const writable = computed(() => canWrite())

const applyQuery = () => router.replace({ query: { ...route.query, q: q.value.trim() || undefined } })
let timer
watch(q, () => { clearTimeout(timer); timer = setTimeout(applyQuery, 300) })
watch(() => route.query.q, (v) => { if ((v || '') !== q.value.trim()) q.value = v || '' })

const fetch = ({ params: p, start, page_length }) => tryCall(() => libraryData.people.list({ space: store.space, kind: p.kind || undefined, q: route.query.q || undefined, area: p.area || undefined, start, page_length }))
</script>
