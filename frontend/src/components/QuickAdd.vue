<template>
  <Dialog v-model:open="open" title="New task" size="lg" position="top">
    <TextInput ref="input" v-model="text" size="md" placeholder="New task. Add a date word such as tomorrow or fri." aria-label="New task" @keydown.enter="add" />
    <Select v-if="(lookups.goals || []).length" v-model="goal" class="mt-2" :options="goalOptions(lookups.goals, { empty: 'No goal' })" aria-label="Goal" data-quick-goal />
    <div class="mt-2 flex flex-wrap justify-between gap-2 text-sm text-ink-gray-6">
      <span>Enter to add to {{ store.space }}. <RouterLink class="text-ink-blue-8 hover:underline" to="/brain" @click="open = false">Add a file in the Brain instead</RouterLink></span>
      <span v-if="last">Added “{{ last }}”</span>
    </div>
  </Dialog>
</template>
<script setup>
// Quick add from anywhere (the n key, or the + button on a phone): one text box, Enter adds, the dialog stays open for the next one.
import { nextTick, ref, watch } from 'vue'
import { Dialog, Select, TextInput } from 'frappe-ui'
import { goalOptions, loadLookups, lookups } from '@/lib/lookups'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'

const open = defineModel('open', { type: Boolean, default: false })
const input = ref(null)
const text = ref('')
const last = ref('')
const goal = ref('')
async function add() {
  const value = text.value.trim()
  if (!value) return
  text.value = ''
  const t = await tryCall(() => api('tasks.quick_add', { text: value, space: store.space, goal: goal.value || undefined }))
  if (t) {
    last.value = t.title + (t.due_date ? `, due ${t.due_date}` : '')
    window.dispatchEvent(new CustomEvent('lifeos-task-added', { detail: t }))
  } else text.value = value
}
watch(open, async (on) => {
  if (!on) return
  last.value = ''
  loadLookups()
  await nextTick()
  input.value?.focus?.()
})
</script>
