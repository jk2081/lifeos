<template>
  <div v-if="c" class="flex flex-col gap-3" data-change :data-change-name="c.name">
    <div class="text-sm text-ink-gray-6">{{ c.change_type }} · {{ c.by }}<template v-if="c.by_agent"> (agent)</template> · {{ dateTime(c.changed_on) }}
      <template v-if="c.source_title"> · from <a class="text-ink-blue-8 hover:underline" href="#" @click.prevent="openSource">{{ c.source_title }}</a></template></div>
    <p v-if="c.change_note" class="text-base text-ink-gray-8">{{ c.change_note }}</p>
    <Badge v-if="c.reverted" theme="gray" label="Undone" />
    <DiffView :before="c.before_md" :after="c.after_md" />
    <template v-if="conflict">
      <Alert theme="amber" title="The page has changed since this change." description="Undoing it now would also remove what was written after it. Below: from the text this change left to the page as it is now." data-undo-conflict />
      <DiffView :before="c.after_md" :after="conflict.current_md" />
      <div class="flex flex-wrap gap-2"><Button theme="red" label="Revert anyway" data-revert-anyway @click="undo(1)" /><Button label="Open the page" @click="openRef('note:' + c.note)" /></div>
    </template>
    <div v-else-if="canUndo" class="flex flex-wrap gap-2">
      <Button label="Undo this change" icon-left="lucide-undo-2" data-undo @click="undo(0)" />
      <Button variant="ghost" label="Open the page" @click="openRef('note:' + c.note)" />
    </div>
  </div>
</template>
<script setup>
// One wiki change: who, when, why, the source that prompted it, and a line diff of the text before and after.
// Undo puts the text from before back if the page has not changed since; otherwise it shows what changed since and asks.
import { libraryData } from '@/data/library'
import { computed, ref, watch } from 'vue'
import { Alert, Badge, Button } from 'frappe-ui'
import DiffView from './DiffView.vue'
import { tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { dateTime } from '@/lib/dates'
import { openRef, recordChanged } from '@/lib/pane'

const props = defineProps({ name: { type: String, required: true } })
const emit = defineEmits(['loaded', 'undone'])
const c = ref(null)
const conflict = ref(null)
const canUndo = computed(() => c.value && !c.value.reverted && ['Created', 'Edited', 'Reverted'].includes(c.value.change_type) && !store.isAgent
  && store.spaces.find((s) => s.name === c.value.space)?.access === 'Write')
async function load() {
  conflict.value = null
  c.value = await tryCall(() => libraryData.wiki.change({ name: props.name }))
  if (c.value) emit('loaded', c.value)
}
async function undo(force) {
  const res = await tryCall(() => libraryData.wiki.undo({ change: c.value.name, force }))
  if (!res) return
  if (res.conflict) { conflict.value = res; return }
  recordChanged('note:' + c.value.note)
  emit('undone', res)
  await load()
}
function openSource() { openRef((c.value.source_doctype === 'Life Chat Log' ? 'chat:' : 'source:') + c.value.source_name) }
watch(() => props.name, load, { immediate: true })
</script>
