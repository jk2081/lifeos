<template>
  <!-- + Capture (issue 14): one box for anything on your mind. It becomes a task at once, or goes to the Brain, which files
       it and asks only if it needs you. Files, a goal, a note or an idea are one tap below. -->
  <Dialog v-model:open="open" title="Capture" size="lg" position="top" data-capture-sheet>
    <div v-if="canWrite()" class="flex flex-col gap-3">
      <Textarea ref="box" v-model="text" :rows="3" placeholder="Anything on your mind. A task with a date word such as tomorrow, a thought, a link."
        aria-label="What to capture" data-capture-text @keydown.meta.enter="toBrain" @keydown.ctrl.enter="toBrain" />
      <div class="flex flex-wrap gap-2">
        <Button variant="solid" label="Add as a task" :loading="busy === 'task'" :disabled="!text.trim() || !!busy" data-capture-task @click="asTask" />
        <Button label="Send to the Brain" :loading="busy === 'brain'" :disabled="!text.trim() || !!busy" data-capture-brain @click="toBrain" />
      </div>
      <div class="flex flex-wrap items-center gap-2 border-t border-outline-gray-1 pt-3" data-capture-more>
        <span class="text-sm text-ink-gray-6">Or add</span>
        <Button v-for="m in MORE" :key="m.key" size="sm" variant="subtle" :icon-left="m.icon" :label="m.label" :data-capture-kind="m.key" @click="m.run" />
      </div>
    </div>
    <p v-else class="text-base text-ink-gray-7">You can read {{ store.space }} but not add to it.</p>
  </Dialog>
</template>
<script setup>
import { nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Button, Dialog, Textarea, toast } from 'frappe-ui'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'

const open = defineModel('open', { type: Boolean, default: false })
const router = useRouter()
const text = ref('')
const busy = ref('')
const box = ref(null)
const close = () => (open.value = false)
const MORE = [
  { key: 'files', label: 'Files or a photo', icon: 'lucide-paperclip', run: () => { close(); router.push({ path: '/brain', query: { capture: 1 } }) } },
  { key: 'goal', label: 'Goal', icon: 'lucide-target', run: () => { close(); store.newKind = 'goal' } },
  { key: 'note', label: 'Note', icon: 'lucide-file-text', run: () => { close(); store.newKind = 'note' } },
  { key: 'idea', label: 'Idea for Someday', icon: 'lucide-lightbulb', run: () => { close(); store.newKind = 'idea' } },
]

async function asTask() {
  const value = text.value.trim()
  if (!value || busy.value) return
  busy.value = 'task'
  const t = await tryCall(() => api('tasks.quick_add', { text: value, space: store.space }))
  busy.value = ''
  if (!t) return
  window.dispatchEvent(new CustomEvent('lifeos-task-added', { detail: t }))
  toast.success(`Added “${t.title}”${t.due_date ? `, due ${t.due_date}` : ''}.`)
  text.value = ''
  close()
}
async function toBrain() {
  const value = text.value.trim()
  if (!value || busy.value) return
  busy.value = 'brain'
  const item = await tryCall(() => api('inbox.create_item', { title: value.split('\n')[0].slice(0, 80), source_type: 'Message', space: store.space,
    raw_text: value, intent: 'Process' }))
  busy.value = ''
  if (!item) return
  window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))
  toast.success('Sent to the Brain. It files it and asks you only if it needs to.')
  text.value = ''
  close()
}
watch(open, async (on) => {
  if (!on) return
  await nextTick()
  box.value?.$el?.querySelector('textarea')?.focus()
})
</script>
