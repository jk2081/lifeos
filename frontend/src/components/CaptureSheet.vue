<template>
  <!-- + Capture (issue 14): one box for anything on your mind. It becomes a task at once, or goes to the Brain, which files
       it and asks only if it needs you. Files, a goal, a note or something for Someday are one tap below. -->
  <Dialog v-model:open="open" title="Capture" size="lg" position="top" data-capture-sheet>
    <div v-if="canWrite()" class="flex flex-col gap-3">
      <Textarea ref="box" v-model="text" :rows="3" placeholder="Anything on your mind. A task with a date word such as tomorrow, a thought, a link."
        aria-label="What to capture" data-capture-text @keydown.meta.enter="toBrain" @keydown.ctrl.enter="toBrain" />
      <!-- files and a photo (moved here from the Inbox's drop zone, issue 17): they wait until Send to the Brain, which makes the capture and uploads each, private -->
      <section v-if="showFiles" class="flex flex-col gap-2 rounded-5 border border-dashed p-3" :class="over ? 'border-outline-gray-5 bg-surface-gray-3' : 'border-outline-gray-3 bg-surface-gray-1'"
        data-dropzone data-capture-files @dragover.prevent="over = true" @dragleave.prevent="over = false" @drop.prevent="onDrop">
        <input ref="picker" type="file" multiple class="hidden" aria-label="Choose files" @change="onPick" />
        <div v-if="!files.length" class="text-sm text-ink-gray-6">Drop files here: a journal photo, a voice note, a PDF, anything. Or
          <Button class="!inline-flex !h-auto !px-0 align-baseline !text-sm underline" size="sm" variant="ghost" label="choose files" @click="picker.click()" /></div>
        <div v-else class="flex flex-wrap items-center gap-1.5">
          <Badge v-for="(f, i) in files" :key="i" size="lg">{{ f.name }} <span class="text-ink-gray-6">{{ fileSize(f.size) }}</span>
            <template #suffix><Button class="!size-4" size="sm" variant="ghost" icon="lucide-x" :label="'Remove ' + f.name" @click="files.splice(i, 1)" /></template></Badge>
          <Button size="sm" variant="outline" icon-left="lucide-plus" label="more" @click="picker.click()" />
        </div>
        <TextInput v-model="instruction" :placeholder="INTENT_HINT[intent]" aria-label="Instruction" />
      </section>
      <TabButtons v-model="intent" :options="INTENTS" aria-label="What to do with it" data-intent />
      <div class="flex flex-wrap gap-2">
        <Button variant="solid" label="Add as a task" :loading="busy === 'task'" :disabled="!text.trim() || !!busy || !!files.length" data-capture-task @click="asTask" />
        <Button label="Send to the Brain" :loading="busy === 'brain'" :disabled="(!text.trim() && !files.length) || !!busy" data-capture-brain @click="toBrain" />
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
import { Badge, Button, Dialog, TabButtons, TextInput, Textarea, toast } from 'frappe-ui'
import { api, errorText, tryCall } from '@/lib/api'
import { fileKind, fileSize, uploadFile } from '@/lib/upload'
import { saveView, savedView } from '@/lib/views'
import { canWrite, store } from '@/lib/store'

const open = defineModel('open', { type: Boolean, default: false })
const router = useRouter()
const text = ref('')
const busy = ref('')
const box = ref(null)
const close = () => (open.value = false)
const showFiles = ref(false)
const files = ref([])
const instruction = ref('')
const over = ref(false)
const picker = ref(null)
// what the agent does with it: propose records (Process), write the wiki (Add to wiki), or only make it searchable (Just keep)
const INTENTS = [{ label: 'Process', value: 'Process' }, { label: 'Add to wiki', value: 'Add to wiki' }, { label: 'Just keep', value: 'Just keep' }]
const INTENT_HINT = { Process: 'What should the agent do? For example: summarise and pull out to-dos', 'Add to wiki': 'Anything the agent should know for the wiki (optional)',
  'Just keep': 'A note to keep with it (optional). It is made searchable; nothing is proposed' }
const intent = ref(savedView('inbox-intent')?.intent || 'Process')
watch(intent, (v) => saveView('inbox-intent', { intent: v }))
function onDrop(e) {
  over.value = false
  files.value.push(...e.dataTransfer.files)
}
function onPick(e) {
  files.value.push(...e.target.files)
  e.target.value = ''
}
function sourceOf() {
  if (!files.value.length) return 'Message'
  const kinds = files.value.map((f) => fileKind(f.name))
  if (kinds.every((k) => k === 'audio')) return 'Voice Note'
  if (kinds.every((k) => k === 'image') && /journal/i.test(instruction.value)) return 'Journal Photo'
  return 'Upload'
}
const MORE = [
  { key: 'files', label: 'Files or a photo', icon: 'lucide-paperclip', run: () => { showFiles.value = true } },
  { key: 'goal', label: 'Goal', icon: 'lucide-target', run: () => { close(); store.newKind = 'goal' } },
  { key: 'note', label: 'Note', icon: 'lucide-file-text', run: () => { close(); store.newKind = 'note' } },
  { key: 'someday', label: 'Park on Someday', icon: 'lucide-lightbulb', run: () => { close(); store.newKind = 'someday' } },
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
  if ((!value && !files.value.length) || busy.value) return
  busy.value = 'brain'
  try {
    const f = files.value
    const title = f.length ? (f.length === 1 ? f[0].name : `${f[0].name} and ${f.length - 1} more`) : value.split('\n')[0].slice(0, 80)
    const item = await api('inbox.create_item', { title, source_type: sourceOf(), space: store.space, instruction: instruction.value, raw_text: value, intent: intent.value })
    for (const file of f) await uploadFile(file, 'Life Inbox Item', item.name)
    window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))
    toast.success(intent.value === 'Just keep' ? 'Kept. The Brain makes it searchable and files it under Activity.' : 'Sent to the Brain. It files it and asks you only if it needs to.')
    text.value = ''
    instruction.value = ''
    files.value = []
    showFiles.value = false
    close()
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.value = ''
  }
}
watch(open, async (on) => {
  if (!on) return
  await nextTick()
  box.value?.$el?.querySelector('textarea')?.focus()
})
</script>
