<template>
  <PageHead title="Library" sub="A page for every person, company and part, written by the Brain from what comes in." />
  <div class="page-body flex max-w-6xl flex-col gap-4" data-library-pages :data-loaded="loaded ? 1 : 0">
    <div class="flex flex-wrap items-center gap-2" data-pages-filters>
      <div class="flex flex-wrap gap-1" role="group" aria-label="Kind" data-pages-kinds>
        <Button v-for="k in KINDS" :key="k.value" size="sm" :variant="kind === k.value ? 'solid' : 'subtle'" :label="k.label + (counts && k.value ? ` · ${counts[k.value]}` : '')" :aria-pressed="kind === k.value"
          :data-pages-kind="k.value" @click="setQuery({ kind: k.value || undefined, status: k.value === 'company' ? status || undefined : undefined })" />
      </div>
      <FormControl class="w-40 max-md:flex-1" type="select" :model-value="status" :options="statusOptions" aria-label="Status" data-pages-status
        @update:model-value="(v) => setQuery({ status: v || undefined, kind: v ? 'company' : kind || undefined })" />
      <TextInput v-model="q" class="w-full min-w-0 sm:w-64" type="search" placeholder="Search pages..." aria-label="Search pages" data-pages-search />
    </div>

    <Card v-if="rows.length" class="!p-0" data-pages-card>
      <ul class="flex flex-col">
        <li v-for="r in rows" :key="r.doctype + r.name" class="border-b border-outline-gray-1 last:border-b-0 hover:bg-surface-gray-1" data-pages-row :data-name="r.name" :data-kind="r.kind" :data-status="r.status || ''">
          <RouterLink class="flex w-full min-w-0 items-start gap-3 px-4 py-3 focus-visible:focus-ring" :to="pagePath(r.doctype, r.name)">
            <span :class="KIND_ICON[r.kind]" class="mt-0.5 size-5 flex-none text-ink-gray-7" aria-hidden="true" />
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2"><span class="break-words text-base-medium text-ink-gray-9" data-pages-title>{{ r.title }}</span>
                <Badge size="sm" :label="LABEL[r.kind]" /><Badge v-if="r.status" theme="blue" size="sm" :label="r.status" data-pages-status-badge /></div>
              <div class="break-words text-sm text-ink-gray-6" data-pages-line>{{ r.path ? r.path + ' · ' : '' }}updated {{ ago(r.updated) }}<span v-if="r.new" data-pages-new> · {{ r.new }} new</span></div>
            </div>
          </RouterLink>
        </li>
      </ul>
    </Card>
    <div v-if="data && rows.length < data.total" class="flex justify-center"><Button label="Show more" :loading="more" data-pages-more @click="loadMore" /></div>

    <Card v-if="loaded && !rows.length" class="py-2" data-pages-empty>
      <Empty :title="filtered ? 'Nothing matches.' : 'No pages yet.'">
        <p class="mt-1">{{ filtered ? 'Try another kind or status, or clear the filters.' : 'A page appears here for each person, company and part that comes up in what you capture and connect, with a brief the Brain writes.' }}</p>
        <Button v-if="filtered" class="mt-3" label="Clear filters" data-pages-clear @click="clear" />
        <Button v-else-if="writable" class="mt-3" variant="solid" icon-left="lucide-plus" label="Capture" data-pages-capture @click="store.captureOpen = true" />
      </Empty>
    </Card>
  </div>
</template>
<script setup>
// Library > Pages (issue 111): the first section of the Library. Every person, company, part and free-form page, filtered by kind (Companies, People, Parts and
// projects, Notes) and by status (Prospect, Client, Partner, Past), the most recently updated first; "n new" is what was linked since you last opened it.
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Badge, Button, FormControl, TextInput } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import PageHead from '@/components/PageHead.vue'
import { tryCall } from '@/lib/api'
import { libraryData } from '@/data/library'
import { canWrite, store } from '@/lib/store'
import { KIND_ICON, pagePath } from '@/lib/pins'
import { onRecordChanged } from '@/lib/pane'

const route = useRoute()
const router = useRouter()
const PAGE = 50
const KINDS = [{ label: 'All', value: '' }, { label: 'Companies', value: 'company' }, { label: 'People', value: 'person' }, { label: 'Parts and projects', value: 'part' }, { label: 'Notes', value: 'note' }]
const LABEL = { company: 'Company', person: 'Person', part: 'Part', note: 'Page' }
const data = ref(null)
const rows = ref([])
const loaded = ref(false)
const more = ref(false)
const q = ref(route.query.q || '')
const kind = computed(() => route.query.kind || '')
const status = computed(() => route.query.status || '')
const statusOptions = computed(() => [{ label: 'Any status', value: '' }, ...(data.value?.statuses || []).map((v) => ({ label: v, value: v }))])
const counts = computed(() => data.value?.counts)
const writable = computed(() => canWrite())
const filtered = computed(() => !!(route.query.q || kind.value || status.value))

const setQuery = (patch) => router.replace({ query: { ...route.query, ...patch } })
let timer
watch(q, () => { clearTimeout(timer); timer = setTimeout(() => setQuery({ q: q.value.trim() || undefined }), 300) })
function clear() { q.value = ''; router.replace({ query: { space: route.query.space } }) }
// "3 days ago", "today": a page is read for when it last changed
function ago(s) {
  const d = Math.floor((Date.now() - new Date(String(s).replace(' ', 'T')).getTime()) / 86400000)
  return d <= 0 ? 'today' : d === 1 ? 'yesterday' : d < 60 ? `${d} days ago` : `${Math.round(d / 30)} months ago`
}

const fetchRows = (start) => tryCall(() => libraryData.pages.index({ space: store.space, kind: kind.value || undefined, status: status.value || undefined, q: route.query.q || undefined, start, page_length: PAGE }))
async function load() {
  const res = await fetchRows(0)
  if (res) { data.value = res; rows.value = res.rows }
  loaded.value = true
}
async function loadMore() {
  more.value = true
  const res = await fetchRows(rows.value.length)
  if (res) rows.value = [...rows.value, ...res.rows]
  more.value = false
}
watch(() => [route.query.kind, route.query.status, route.query.q, store.space], load)
onRecordChanged(load)
onMounted(load)
</script>
