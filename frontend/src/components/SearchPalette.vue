<template>
  <CommandPalette v-model:open="open" v-model:query="text" :filterable="false" title="Search" @select="go">
    <CommandPaletteInput placeholder="Search notes, tasks, inbox items, chats and the vault" aria-label="Search" />
    <CommandPaletteList>
      <CommandPaletteItem v-for="r in results" :key="r.ref_name + r.kind" :value="r" :label="r.title || 'Untitled'" data-search-hit>
        <div class="flex min-w-0 flex-col gap-0.5 py-0.5">
          <span class="truncate text-base-medium text-ink-gray-9">{{ r.title || 'Untitled' }}</span>
          <span class="truncate text-sm text-ink-gray-6">{{ [multi && r.space, r.area_name, short(r.record_date, true), r.is_archived ? 'archived' : ''].filter(Boolean).join(' · ') }}</span>
          <span v-if="r.snippet" class="truncate text-sm text-ink-gray-6">{{ r.snippet }}</span>
        </div>
        <template #suffix><Badge :label="KIND[r.kind] || r.kind" /></template>
      </CommandPaletteItem>
    </CommandPaletteList>
    <CommandPaletteEmpty>
      <Empty v-if="searched" :title="`Nothing found for “${searched}”.`" :hint="`Try fewer words${archived ? '' : ', or include archived records'}.`" />
      <Empty v-else title="Search everything you can see." hint="Type a word from a title, a note or a transcript." />
    </CommandPaletteEmpty>
    <CommandPaletteFooter>
      <div class="flex w-full flex-wrap items-center justify-between gap-2">
        <Checkbox v-model="archived" label="Include archived" />
        <span class="flex items-center gap-1 text-sm text-ink-gray-6"><KeyboardShortcut bg combo="ArrowUp" use-icons /><KeyboardShortcut bg combo="ArrowDown" use-icons /> to move,
          <KeyboardShortcut bg combo="Enter" use-icons /> to open</span>
      </div>
    </CommandPaletteFooter>
  </CommandPalette>
</template>
<script setup>
// Search over everything the person can see. frappe-ui's experimental CommandPalette draws it; the results come from
// our own search method, which applies the space rules. A result opens in the pane over the screen you are on.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Checkbox, KeyboardShortcut } from 'frappe-ui'
import { CommandPalette, CommandPaletteEmpty, CommandPaletteFooter, CommandPaletteInput, CommandPaletteItem, CommandPaletteList } from '@/experimental'
import Empty from './Empty.vue'
import { api } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { openRef, refOf } from '@/lib/pane'

const open = defineModel('open', { type: Boolean, default: false })
const KIND = { Inbox: 'Inbox item', 'Journal Page': 'Journal page', 'Month Plan': 'Month plan' }
const router = useRouter()
const text = ref('')
const results = ref([])
const searched = ref('')
const archived = ref(false)
const multi = computed(() => store.spaces.length > 1)
let timer = null
let seq = 0

async function run() {
  const q = text.value.trim()
  if (!q) {
    results.value = []
    searched.value = ''
    return
  }
  const mine = ++seq
  try {
    const res = await api('search.query', { text: q, limit: 20, include_archived: archived.value ? 1 : 0 })
    if (mine !== seq) return
    results.value = res.results
    searched.value = q
  } catch (e) {
    results.value = []
  }
}
watch([text, archived], () => {
  clearTimeout(timer)
  timer = setTimeout(run, 180)
})
watch(open, (on) => { if (!on) { results.value = []; searched.value = '' } })
function go(r) {
  if (!r) return
  if (r.space && r.space !== store.space) store.space = r.space
  const ref = refOf(r.ref_doctype, r.ref_name)
  ref ? openRef(ref) : router.push(r.route)
}
</script>
