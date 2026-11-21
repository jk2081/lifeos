<template>
  <PageHead title="Library" sub="Every person and organisation, with everything Life OS knows about them." />
  <div class="page-body flex max-w-6xl flex-col gap-4" data-library-people :data-loaded="loaded ? 1 : 0">
    <div class="flex flex-wrap items-center gap-2" data-people-filters>
      <TextInput v-model="q" class="w-full min-w-0 sm:w-80" type="search" placeholder="Search people and organisations..." aria-label="Search people and organisations" data-people-search @keydown.enter="applyQuery" />
      <select class="h-8 w-40 max-w-full rounded border border-outline-gray-2 bg-surface-base px-2 py-0 text-sm leading-5 text-ink-gray-8 focus-visible:focus-ring max-md:h-10 max-md:flex-1" :value="kind" aria-label="Kind" data-people-kind
        @change="(e) => setQuery({ kind: e.target.value || undefined })"><option v-for="o in KINDS" :key="o.value" :value="o.value">{{ o.label }}</option></select>
      <select class="h-8 w-36 max-w-full rounded border border-outline-gray-2 bg-surface-base px-2 py-0 text-sm leading-5 text-ink-gray-8 focus-visible:focus-ring max-md:h-10 max-md:flex-1" :value="area" aria-label="Area" data-people-area
        @change="(e) => setQuery({ area: e.target.value || undefined })"><option v-for="o in areaChoices" :key="o.value" :value="o.value">{{ o.label }}</option></select>
      <span v-if="loaded" class="ml-auto text-sm tabular-nums text-ink-gray-6" data-people-count>{{ data.total.toLocaleString() }} {{ data.total === 1 ? 'entry' : 'entries' }}</span>
    </div>

    <Card v-if="rows.length" class="!p-0" data-people-card>
      <ul class="flex flex-col">
        <li v-for="r in rows" :key="r.name" class="relative border-b border-outline-gray-1 last:border-b-0 hover:bg-surface-gray-1" data-people-row :data-name="r.name" :data-kind="r.kind">
          <button type="button" class="flex w-full min-w-0 flex-col gap-1 px-4 py-3 text-left md:grid md:grid-cols-[2rem_minmax(0,1fr)_minmax(0,9rem)_minmax(0,16rem)] md:items-center md:gap-4 focus-visible:focus-ring"
            @click="router.push({ path: `/library/people/${r.name}`, query: { space: route.query.space } })">
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
          </button>
        </li>
      </ul>
    </Card>
    <div v-if="data && rows.length < data.total" class="flex justify-center"><Button label="Show more" :loading="more" data-people-more @click="loadMore" /></div>

    <Card v-if="loaded && !rows.length" class="py-2" data-people-empty>
      <Empty :title="filtered ? 'Nothing matches.' : 'No people or organisations yet.'">
        <p class="mt-1">{{ filtered ? 'Try a different word, or clear the filters.' : 'People and organisations you capture, or the Brain finds in what you keep, will show up here.' }}</p>
        <Button v-if="filtered" class="mt-3" label="Clear filters" data-people-clear @click="clear" />
        <Button v-else-if="writable" class="mt-3" variant="solid" icon-left="lucide-plus" label="Capture" data-people-capture @click="store.captureOpen = true" />
      </Empty>
    </Card>
  </div>
</template>
<script setup>
// Library > People (issue 25): one row per person or organisation with its kind, a line about them, area and the newest thing
// that mentions them. Kind, Area and the search narrow the list (kind, area and q live in the address). A row opens the person's page.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, TextInput } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import PageHead from '@/components/PageHead.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { areaOptions, loadLookups } from '@/lib/lookups'
import { onRecordChanged } from '@/lib/pane'

const route = useRoute()
const router = useRouter()
const PAGE = 50
const KINDS = [{ label: 'People and organisations', value: '' }, { label: 'People', value: 'Person' }, { label: 'Organisations', value: 'Organisation' }]
const data = ref(null)
const rows = ref([])
const loaded = ref(false)
const more = ref(false)
const q = ref(route.query.q || '')
const kind = computed(() => route.query.kind || '')
const area = computed(() => route.query.area || '')
const writable = computed(() => canWrite())
const filtered = computed(() => !!(route.query.q || kind.value || area.value))
const areaChoices = computed(() => [{ label: 'Area', value: '' }, ...areaOptions()])

const setQuery = (patch) => router.replace({ query: { ...route.query, ...patch, open: route.query.open } })
const applyQuery = () => setQuery({ q: q.value.trim() || undefined })
let timer
watch(q, () => { clearTimeout(timer); timer = setTimeout(applyQuery, 300) })
function clear() { q.value = ''; router.replace({ query: { space: route.query.space } }) }

const fetchRows = (start) => tryCall(() => api('people.list', { space: store.space, kind: kind.value || undefined, q: route.query.q || undefined,
  area: area.value || store.lensArea || undefined, start, page_length: PAGE }))
async function load() {
  const res = await fetchRows(0)
  if (res) { data.value = res; rows.value = res.rows }
  loaded.value = true
}
async function loadMore() {
  more.value = true
  const res = await fetchRows(rows.value.length)
  if (res) { data.value = res; rows.value = [...rows.value, ...res.rows] }
  more.value = false
}
watch(() => [route.query.q, route.query.kind, route.query.area, store.space, store.lensArea], load)
onRecordChanged(load)
onMounted(() => { loadLookups(); load() })
</script>
