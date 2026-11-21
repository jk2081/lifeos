<template>
  <PageHead title="Library" sub="Everything you know, kept and searchable. Filed here by you or by the Brain." />
  <div class="page-body flex max-w-6xl flex-col gap-4" data-library-everything :data-lib-tab="tab" :data-loaded="loaded ? 1 : 0">
    <div class="flex flex-wrap items-center gap-2" data-lib-filters>
      <TextInput v-model="q" class="w-full min-w-0 sm:w-80" type="search" :placeholder="`Search ${PLACEHOLDER[tab]}...`" aria-label="Search the Library" data-lib-search @keydown.enter="applyQuery" />
      <select class="h-8 w-36 max-w-full rounded border border-outline-gray-2 bg-surface-base px-2 py-0 text-sm leading-5 text-ink-gray-8 focus-visible:focus-ring max-md:h-10 max-md:flex-1" :value="area" aria-label="Area" data-lib-area
        @change="(e) => setQuery({ area: e.target.value || undefined })"><option v-for="o in areaChoices" :key="o.value" :value="o.value">{{ o.label }}</option></select>
      <select class="h-8 w-36 max-w-full rounded border border-outline-gray-2 bg-surface-base px-2 py-0 text-sm leading-5 text-ink-gray-8 focus-visible:focus-ring max-md:h-10 max-md:flex-1" :value="goal" aria-label="Goal" data-lib-goal
        @change="(e) => setQuery({ goal: e.target.value || undefined })"><option v-for="o in goalChoices" :key="o.value" :value="o.value">{{ o.label }}</option></select>
      <select class="h-8 w-36 max-w-full rounded border border-outline-gray-2 bg-surface-base px-2 py-0 text-sm leading-5 text-ink-gray-8 focus-visible:focus-ring max-md:h-10 max-md:flex-1" :value="source" aria-label="Source" data-lib-source
        @change="(e) => setQuery({ source: e.target.value || undefined })"><option v-for="o in sourceChoices" :key="o.value" :value="o.value">{{ o.label }}</option></select>
      <span v-if="loaded" class="ml-auto text-sm tabular-nums text-ink-gray-6" data-lib-count>{{ data.total.toLocaleString() }} item{{ data.total === 1 ? '' : 's' }}</span>
    </div>

    <Card v-if="rows.length" class="!p-0" data-lib-card>
      <ul class="flex flex-col">
        <li v-for="r in rows" :key="r.ref" class="relative border-b border-outline-gray-1 last:border-b-0 hover:bg-surface-gray-1" data-lib-row :data-ref="r.ref" :data-kind="r.kind" :data-letter="r.letter">
          <component :is="clickable(r) ? 'button' : 'div'" :type="clickable(r) ? 'button' : undefined"
            class="flex w-full min-w-0 flex-col gap-1 px-4 py-3 text-left md:grid md:grid-cols-[2rem_minmax(0,1fr)_minmax(0,16rem)_4.5rem] md:items-center md:gap-4 focus-visible:focus-ring" @click="clickable(r) && openRef(r.ref)">
            <div class="flex min-w-0 items-start gap-3 md:contents">
              <span class="flex size-8 flex-none items-center justify-center rounded-md text-sm-medium" :class="LETTER_CLASS[r.letter]" aria-hidden="true" data-lib-letter>{{ r.letter }}</span>
              <div class="min-w-0 flex-1">
                <div class="break-words text-base-medium text-ink-gray-9" data-lib-title>{{ r.title }}</div>
                <div class="break-words text-sm text-ink-gray-6" data-lib-line>{{ r.line }}<span v-if="r.sensitive" role="img" aria-label="Sensitive" data-sensitive-lock> 🔒</span>
                  <Badge v-if="r.expiry" class="ml-1" size="sm" :theme="r.expiry.state === 'expired' ? 'red' : 'amber'" :label="r.expiry.state === 'expired' ? 'Expired' : `Expires in ${r.expiry.days} days`" data-expiry-badge /></div>
              </div>
            </div>
            <div class="min-w-0 truncate pl-11 text-sm text-ink-gray-7 md:pl-0 md:text-base" data-lib-where>{{ [r.area_name, r.goal_title].filter(Boolean).join(' · ') }}</div>
            <div class="whitespace-nowrap pl-11 text-sm text-ink-gray-6 md:pl-0 md:text-right" data-lib-date>{{ short(r.date) }}</div>
          </component>
        </li>
      </ul>
    </Card>
    <div v-if="data && rows.length < data.total" class="flex justify-center"><Button label="Show more" :loading="more" data-lib-more @click="loadMore" /></div>

    <Card v-if="loaded && !rows.length" class="py-2" data-lib-empty>
      <Empty :title="filtered ? 'Nothing matches.' : tab === 'people' ? 'No people kept yet.' : 'Nothing kept yet.'">
        <p class="mt-1">{{ filtered ? 'Try a different word, or clear the filters.' : 'Notes, documents, people and chats you keep, or the Brain files for you, will show up here.' }}</p>
        <Button v-if="filtered" class="mt-3" label="Clear filters" data-lib-clear @click="clear" />
        <Button v-else-if="writable" class="mt-3" variant="solid" icon-left="lucide-plus" label="Capture" data-lib-capture @click="store.captureOpen = true" />
      </Empty>
    </Card>
  </div>
</template>
<script setup>
// Library > Everything and Library > People (issue 23): notes, documents, people and chats in one list, newest first. Each row has a
// kind letter (N, P, D, C), a title, a line about it, its area and goal, and a date. The search box reads titles and bodies;
// Area, Goal and Source narrow the list. Filters live in the address (q, area, goal, source). Sensitive items follow the Vault's rules on the server.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, TextInput } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import PageHead from '@/components/PageHead.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { areaOptions, goalOptions, loadLookups, lookups } from '@/lib/lookups'
import { onRecordChanged, openRef } from '@/lib/pane'

const props = defineProps({ tab: { type: String, default: 'all' } })
const route = useRoute()
const router = useRouter()
const PAGE = 50
const PLACEHOLDER = { all: 'notes, documents, people, chats', people: 'people' }
const LETTER_CLASS = { N: 'bg-surface-gray-2 text-ink-gray-7', P: 'bg-surface-blue-2 text-ink-gray-9', D: 'bg-surface-amber-2 text-ink-gray-9', C: 'bg-surface-violet-1 text-ink-violet-8' }
const data = ref(null)
const rows = ref([])
const loaded = ref(false)
const more = ref(false)
const q = ref(route.query.q || '')
const area = computed(() => route.query.area || '')
const goal = computed(() => route.query.goal || '')
const source = computed(() => route.query.source || '')
const writable = computed(() => canWrite())
const filtered = computed(() => !!(route.query.q || area.value || goal.value || source.value))
const areaChoices = computed(() => [{ label: 'Area', value: '' }, ...areaOptions()])
const goalChoices = computed(() => [{ label: 'Goal', value: '' }, { label: 'No goal', value: 'none' }, ...goalOptions(lookups.goals, { empty: null })])
const sourceChoices = computed(() => [{ label: 'Source', value: '' }, { label: 'Made by me', value: 'me' }, { label: 'Kept by the Brain', value: 'brain' },
  ...(data.value?.sources || []).map((s) => ({ label: s.charAt(0).toUpperCase() + s.slice(1), value: s }))])
// a Life Person has no page of its own until the People issue; every other row opens in the pane
const clickable = (r) => r.doctype !== 'Life Person'

const setQuery = (patch) => router.replace({ query: { ...route.query, ...patch, open: route.query.open } })
const applyQuery = () => setQuery({ q: q.value.trim() || undefined })
let timer
watch(q, () => { clearTimeout(timer); timer = setTimeout(applyQuery, 300) })
function clear() { q.value = ''; router.replace({ query: { space: route.query.space, open: route.query.open } }) }

async function fetchRows(start) {
  return tryCall(() => api('everything.list', { space: store.space, tab: props.tab, q: route.query.q || undefined, area: area.value || store.lensArea || undefined,
    goal: goal.value || undefined, source: source.value || undefined, start, page_length: PAGE }))
}
async function load() {
  const res = await fetchRows(0)
  if (res) { data.value = res; rows.value = res.rows }
  loaded.value = true
}
async function loadMore() {
  more.value = true
  const res = await fetchRows(rows.value.length)
  if (res) { data.value = { ...res, sources: res.sources }; rows.value = [...rows.value, ...res.rows] }
  more.value = false
}
watch(() => [route.query.q, route.query.area, route.query.goal, route.query.source, store.space, store.lensArea, props.tab], load)
onRecordChanged(load)
onMounted(() => { loadLookups(); load() })
</script>
