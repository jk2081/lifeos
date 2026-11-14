<template>
  <Dialog v-model="open" :title="goal ? 'Edit goal' : 'Add goal'" size="lg">
    <div style="display: flex; flex-direction: column; gap: 12px">
      <div class="field"><label class="lbl" for="gd-title">Goal</label><input id="gd-title" v-model="form.title" class="inp" placeholder="For example: Golf: hit 5 birdies" /></div>
      <div class="field"><label class="lbl" for="gd-area">Area</label>
        <select id="gd-area" v-model="form.area" class="inp"><option value="">—</option><option v-for="o in areaOptions()" :key="o.value" :value="o.value">{{ o.label }}</option></select></div>
      <div class="field"><span class="lbl">Actions, and how many times a week</span>
        <div v-for="(a, i) in form.actions" :key="i" style="display: flex; gap: 8px; margin-bottom: 6px">
          <input v-model="a.title" class="inp" style="flex: 1" :aria-label="`Action ${i + 1}`" placeholder="Action" />
          <input v-model.number="a.per_week" type="number" min="1" max="7" class="inp" style="width: 64px" :aria-label="`Times a week for action ${i + 1}`" />
          <button class="bt s ic" type="button" aria-label="Remove action" @click="form.actions.splice(i, 1)">×</button>
        </div>
        <button class="ch sm add" type="button" @click="form.actions.push({ title: '', per_week: 1 })">+ action</button>
      </div>
    </div>
    <template #actions><div style="display: flex; gap: 8px; justify-content: space-between">
      <button v-if="goal" class="bt t" type="button" style="color: var(--r-ink)" @click="remove">Delete goal</button><span v-else></span>
      <div style="display: flex; gap: 8px"><button class="bt s" type="button" @click="open = false">Cancel</button>
        <button class="bt p" type="button" @click="save">Save goal</button></div></div></template>
  </Dialog>
</template>
<script setup>
import { reactive, ref, watch } from 'vue'
import { Dialog } from 'frappe-ui'
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
  const res = await tryCall(() => api('journal.save_goal', { goal: props.goal?.name, cycle: props.cycle, title: form.title, area: form.area, actions: form.actions }), 'Goal saved.')
  if (res) {
    open.value = false
    emit('saved')
  }
}
async function remove() {
  if (!window.confirm('Delete this goal and its ticks?')) return
  if (await tryCall(() => api('journal.delete_goal', { goal: props.goal.name }), 'Goal deleted.')) {
    open.value = false
    emit('saved')
  }
}
</script>
