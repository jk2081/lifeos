<template>
  <Dialog v-model:open="open" :title="goal ? 'Edit goal' : 'Add goal'" size="lg">
    <div class="flex flex-col gap-3">
      <FormControl v-model="form.title" label="Goal" placeholder="For example: Golf: hit 5 birdies" />
      <FormControl v-model="form.area" type="select" label="Area" :options="[{ label: '—', value: '' }, ...areaOptions()]" />
      <div>
        <div class="mb-1.5 text-sm text-ink-gray-6">Actions, and how many times a week</div>
        <div v-for="(a, i) in form.actions" :key="i" class="mb-1.5 flex gap-2">
          <TextInput v-model="a.title" class="min-w-0 flex-1" :aria-label="`Action ${i + 1}`" placeholder="Action" />
          <TextInput v-model.number="a.per_week" class="w-16" type="number" min="1" max="7" :aria-label="`Times a week for action ${i + 1}`" />
          <Button icon="lucide-x" label="Remove action" @click="form.actions.splice(i, 1)" />
        </div>
        <Button size="sm" variant="outline" icon-left="lucide-plus" label="action" @click="form.actions.push({ title: '', per_week: 1 })" />
      </div>
    </div>
    <template #actions><div class="flex justify-between gap-2">
      <Button v-if="goal" variant="ghost" theme="red" label="Delete goal" @click="remove" /><span v-else></span>
      <div class="flex gap-2"><Button label="Cancel" @click="open = false" />
        <Button variant="solid" label="Save goal" @click="save" /></div></div></template>
  </Dialog>
</template>
<script setup>
import { reactive, ref, watch } from 'vue'
import { Button, Dialog, FormControl, TextInput, dialog } from 'frappe-ui'
import { api, tryCall } from '@/lib/api'
import { areaOptions, loadLookups } from '@/lib/lookups'

const props = defineProps({ modelValue: Boolean, cycle: String, goal: Object })
const emit = defineEmits(['update:modelValue', 'saved'])
const open = ref(false)
const form = reactive({ title: '', area: '', actions: [] })
watch(() => props.modelValue, (v) => {
  open.value = v
  if (v) {
    loadLookups()
    const g = props.goal
    Object.assign(form, { title: g?.title || '', area: g?.area || '', actions: g ? g.actions.map((a) => ({ name: a.name, title: a.title, per_week: a.per_week })) : [{ title: '', per_week: 1 }] })
  }
})
watch(open, (v) => emit('update:modelValue', v))
async function save() {
  const res = await tryCall(() => api('journal.save_goal', { goal: props.goal?.name, cycle: props.cycle, title: form.title, area: form.area || '', actions: form.actions }), 'Goal saved.')
  if (res) {
    open.value = false
    emit('saved')
  }
}
function remove() {
  dialog.danger({
    title: 'Delete goal',
    message: 'Delete this goal and its ticks?',
    confirmLabel: 'Delete goal',
    onConfirm: async () => {
      if (await tryCall(() => api('journal.delete_goal', { goal: props.goal.name }), 'Goal deleted.')) {
        open.value = false
        emit('saved')
      }
    },
  })
}
</script>
