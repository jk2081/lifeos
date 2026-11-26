<template>
  <PageHead title="Library" sub="Every file once, with where it is used." />
  <div class="page-body flex max-w-6xl flex-col gap-4" data-library-files :data-loaded="loaded ? 1 : 0">
    <div class="flex flex-wrap items-center gap-2" data-files-filters>
      <TextInput v-model="q" class="w-full min-w-0 sm:w-80" type="search" placeholder="Search files by name..." aria-label="Search files by name" data-files-search @keydown.enter="applyQuery" />
      <Select class="w-36 max-md:flex-1" :model-value="type" :options="TYPES" aria-label="Type" data-files-type @update:model-value="(v) => setQuery({ type: v || undefined })" />
      <Select class="w-36 max-md:flex-1" :model-value="area" :options="areaChoices" aria-label="Area" data-files-area @update:model-value="(v) => setQuery({ area: v || undefined })" />
      <Select class="w-36 max-md:flex-1" :model-value="source" :options="sourceChoices" aria-label="Source" data-files-source @update:model-value="(v) => setQuery({ source: v || undefined })" />
      <span v-if="loaded" class="ml-auto text-sm tabular-nums text-ink-gray-6" data-files-count>{{ data.total.toLocaleString() }} file{{ data.total === 1 ? '' : 's' }}</span>
    </div>

    <Card v-if="rows.length" class="!p-0" data-files-card>
      <ul class="flex flex-col">
        <li v-for="r in rows" :key="r.key" class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-3 last:border-b-0 md:grid md:grid-cols-[2rem_minmax(0,1fr)_minmax(0,18rem)_auto] md:items-start md:gap-4" data-file-row :data-name="r.name" :data-type="r.type">
          <div class="flex min-w-0 items-start gap-3 md:contents">
            <span class="flex size-8 flex-none items-center justify-center rounded-md text-sm-medium" :class="LETTER_CLASS[r.type]" aria-hidden="true">{{ r.letter }}</span>
            <div class="min-w-0 flex-1">
              <div class="break-words text-base-medium text-ink-gray-9" data-file-name>{{ r.name }}</div>
              <div class="break-words text-sm text-ink-gray-6" data-file-line>{{ line(r) }}
                <Badge v-if="r.reusable" class="ml-1" size="sm" theme="blue" :label="`Reusable · ${r.jobs} job${r.jobs === 1 ? '' : 's'}`" data-file-reusable />
              </div>
              <div v-if="r.version_count > 1" class="mt-1">
                <Button variant="ghost" size="sm" icon-left="lucide-history" :label="`${r.version_count} versions`" :aria-expanded="open[r.key] ? 'true' : 'false'" data-file-versions @click="open[r.key] = !open[r.key]" />
                <ul v-if="open[r.key]" class="mt-1 flex flex-col gap-1 text-sm" data-file-version-list>
                  <li v-for="v in r.versions" :key="v.url" class="flex flex-wrap gap-x-2">
                    <a class="text-ink-blue-8 hover:underline" :href="v.url" target="_blank" rel="noopener" data-file-version>{{ v.current ? 'Latest' : 'Earlier' }}, {{ short(v.date) }}</a>
                    <span class="text-ink-gray-6">{{ fileSize(v.size) }}</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
          <div class="min-w-0 pl-11 text-sm md:pl-0" data-file-used>
            <span class="text-ink-gray-6">Used in</span>
            <ul class="mt-0.5 flex flex-col gap-0.5">
              <li v-for="u in r.used_in" :key="u.ref" class="min-w-0"><button type="button" class="max-w-full truncate text-left text-ink-blue-8 hover:underline focus-visible:focus-ring" data-file-used-in :data-ref="u.ref" @click="openRef(u.ref)">{{ u.title }}</button></li>
            </ul>
          </div>
          <div class="flex flex-wrap items-center gap-2 pl-11 md:pl-0">
            <a class="inline-flex h-7 items-center rounded border border-outline-gray-2 px-2 text-sm text-ink-gray-8 hover:bg-surface-gray-2 focus-visible:focus-ring" :href="r.url" target="_blank" rel="noopener" data-file-open>Open</a>
            <a class="inline-flex h-7 items-center rounded border border-outline-gray-2 px-2 text-sm text-ink-gray-8 hover:bg-surface-gray-2 focus-visible:focus-ring" :href="r.url" :download="r.name" data-file-download>Download</a>
          </div>
        </li>
      </ul>
    </Card>
    <div v-if="data && rows.length < data.total" class="flex justify-center"><Button label="Show more" :loading="more" data-files-more @click="loadMore" /></div>

    <Card v-if="loaded && !rows.length" class="py-2" data-files-empty>
      <Empty :title="filtered ? 'No file matches.' : 'No files kept yet.'">
        <p class="mt-1">{{ filtered ? 'Try a different name, or clear the filters.' : 'Files you capture or the Brain files for you will show up here, each once.' }}</p>
        <Button v-if="filtered" class="mt-3" label="Clear filters" data-files-clear @click="clear" />
        <Button v-else-if="writable" class="mt-3" variant="solid" icon-left="lucide-message-square" label="Chat" data-files-capture @click="openChat()" />
      </Empty>
    </Card>
  </div>
</template>
<script setup>
import { openChat } from '@/lib/ask'
// Library > Files (issue 24): every stored file once (issue 7 keeps one copy per space), with its type, size, date, earlier
// versions and the records that use it. Open shows it in the browser where it can; Download saves it. Filters live in the address.
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Select, TextInput } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import PageHead from '@/components/PageHead.vue'
import { tryCall } from '@/lib/api'
import { libraryData } from '@/data/library'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { fileSize } from '@/lib/upload'
import { areaOptions, loadLookups } from '@/lib/lookups'
import { onRecordChanged, openRef } from '@/lib/pane'

const route = useRoute()
const router = useRouter()
const PAGE = 50
const TYPES = [{ label: 'Type', value: '' }, { label: 'Documents', value: 'documents' }, { label: 'Images', value: 'images' }, { label: 'Slides', value: 'slides' },
  { label: 'Audio', value: 'audio' }, { label: 'Other', value: 'other' }]
const KIND = { documents: 'Document', images: 'Image', slides: 'Slides', audio: 'Audio', other: 'File' }
const LETTER_CLASS = { documents: 'bg-surface-amber-2 text-ink-gray-9', images: 'bg-surface-blue-2 text-ink-gray-9', slides: 'bg-surface-violet-1 text-ink-violet-8',
  audio: 'bg-surface-gray-2 text-ink-gray-7', other: 'bg-surface-gray-2 text-ink-gray-7' }
const data = ref(null)
const rows = ref([])
const loaded = ref(false)
const more = ref(false)
const open = reactive({})
const q = ref(route.query.q || '')
const type = computed(() => route.query.type || '')
const area = computed(() => route.query.area || '')
const source = computed(() => route.query.source || '')
const writable = computed(() => canWrite())
const filtered = computed(() => !!(route.query.q || type.value || area.value || source.value))
const areaChoices = computed(() => [{ label: 'Area', value: '' }, ...areaOptions()])
const sourceChoices = computed(() => [{ label: 'Source', value: '' }, { label: 'Made by me', value: 'me' }, { label: 'Kept by the Brain', value: 'brain' },
  ...(data.value?.sources || []).map((s) => ({ label: s.charAt(0).toUpperCase() + s.slice(1), value: s }))])
const line = (r) => [KIND[r.type], fileSize(r.size), short(r.date)].filter(Boolean).join(' · ')

const setQuery = (patch) => router.replace({ query: { ...route.query, ...patch, open: route.query.open } })
const applyQuery = () => setQuery({ q: q.value.trim() || undefined })
let timer
watch(q, () => { clearTimeout(timer); timer = setTimeout(applyQuery, 300) })
function clear() { q.value = ''; router.replace({ query: { space: route.query.space, open: route.query.open } }) }

const fetchRows = (start) => tryCall(() => libraryData.files.list({ space: store.space, q: route.query.q || undefined, type: type.value || undefined,
  area: area.value || store.lensArea || undefined, source: source.value || undefined, start, page_length: PAGE }))
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
watch(() => [route.query.q, route.query.type, route.query.area, route.query.source, store.space, store.lensArea], load)
onRecordChanged(load)
onMounted(() => { loadLookups(); load() })
</script>
