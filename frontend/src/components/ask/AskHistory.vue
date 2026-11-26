<template>
  <div class="flex flex-col gap-3 px-4 py-4" data-ask-history>
    <TextInput :model-value="q" placeholder="Search your earlier chats" aria-label="Search history" @update:model-value="(v) => { q = v; load() }" />
    <div v-for="t in rows" :key="t.name" class="flex items-center gap-2 border-b border-outline-gray-1 py-2 last:border-b-0" data-history-row>
      <div class="min-w-0 flex-1"><a href="#" class="break-words text-base text-ink-gray-9 hover:underline focus-visible:focus-ring" @click.prevent="open(t.name)">{{ t.title }}</a>
        <div class="text-sm text-ink-gray-6">{{ [t.channel ? 'on ' + t.channel : t.scope_label, t.questions + (t.channel ? ' message' : ' question') + (t.questions === 1 ? '' : 's'), t.last_message_on].filter(Boolean).join(' · ') }}</div></div>
      <Button variant="ghost" icon="lucide-trash-2" :label="'Delete ' + t.title" data-history-delete @click="remove(t)" />
    </div>
    <Empty v-if="!rows.length" title="No earlier chats." hint="What you chat about is kept here, for you only." />
  </div>
</template>
<script setup>
// Earlier conversations: searchable, openable, deletable. The one ongoing conversation is the newest.
import { onMounted, ref } from 'vue'
import { Button, TextInput, dialog } from 'frappe-ui'
import Empty from '../Empty.vue'
import { api } from '@/lib/api'
import { ask, loadThread, newChat } from '@/lib/ask'
import { store } from '@/lib/store'

const rows = ref([])
const q = ref('')
async function load() {
  try { rows.value = (await api('chat.threads', { space: store.space, q: q.value || undefined })).rows } catch (e) { rows.value = [] }
}
const open = (name) => loadThread(name)
function remove(t) {
  dialog.danger({ title: 'Delete this chat?', message: `“${t.title}” and its answers are deleted for good.`, confirmLabel: 'Delete',
    onConfirm: async () => { await api('chat.delete_thread', { name: t.name }); if (ask.thread === t.name) newChat(); ask.view = 'history'; load() } })
}
onMounted(load)
</script>
