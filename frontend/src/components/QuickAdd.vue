<template>
  <div class="qa-back" @click.self="$emit('close')">
    <div class="qa" role="dialog" aria-label="New task">
      <input ref="input" v-model="text" class="inp" style="width: 100%; height: 40px" placeholder="New task. Add a date word such as tomorrow or fri."
        @keydown.enter="add" @keydown.esc="$emit('close')" />
      <div class="mt" style="margin-top: 8px; display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap">
        <span>Enter to add to {{ store.space }}. <RouterLink to="/inbox" @click="$emit('close')">Add a file to the Inbox instead</RouterLink></span>
        <span v-if="last">Added “{{ last }}”</span>
      </div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'

defineEmits(['close'])
const input = ref(null)
const text = ref('')
const last = ref('')
async function add() {
  const value = text.value.trim()
  if (!value) return
  text.value = ''
  const t = await tryCall(() => api('tasks.quick_add', { text: value, space: store.space }))
  if (t) {
    last.value = t.title + (t.due_date ? `, due ${t.due_date}` : '')
    window.dispatchEvent(new CustomEvent('lifeos-task-added', { detail: t }))
  } else text.value = value
}
onMounted(() => input.value?.focus())
</script>
<style scoped>
.qa-back { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.25); z-index: 60; display: flex; justify-content: center; align-items: flex-start; padding: 12vh 16px 0; }
.qa { width: min(560px, 100%); background: var(--surface-base); border: 1px solid var(--outline-gray-1); border-radius: 12px; padding: 14px; box-shadow: var(--elevation-lg); }
</style>
