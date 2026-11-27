<template>
  <OptionPicker :model-value="modelValue" :items="items" v-model:query="query" :shown="shown" :label="label" :placeholder="placeholder" :loading="loading" :disabled="disabled" prefix="person"
    search-placeholder="Search by name, company or email" empty-text="No one found" @update:model-value="(v) => emit('update:modelValue', v)" @picked="(v) => emit('picked', known[v])"
    @open="search" />
</template>
<script setup>
// One searchable person picker (issue 136): people only, each with their company under the name, a search that also matches the company and the email, and the
// server answering as you type so no one is out of reach. At the end, "Add 'x' as a person" when nothing matches exactly. On a phone it opens as a sheet.
import { computed, ref, watch } from 'vue'
import { toast } from 'frappe-ui'
import { useDebounceFn } from '@vueuse/core'
import OptionPicker from './OptionPicker.vue'
import { tryCall } from '@/lib/api'
import { itemData } from '@/data/item'
import { store } from '@/lib/store'

const props = defineProps({ modelValue: { type: String, default: '' }, space: { type: String, default: '' }, label: { type: String, default: '' }, placeholder: { type: String, default: 'Choose a person' },
  disabled: Boolean, allowNew: { type: Boolean, default: true } })
const emit = defineEmits(['update:modelValue', 'added', 'picked'])
const query = ref('')
const rows = ref([])
const known = ref({}) // everyone seen so far, so the chosen person keeps their name when the list changes
const loading = ref(false)
let asked = 0

async function search() {
  const mine = ++asked
  loading.value = true
  const out = await tryCall(() => itemData.people.options({ space: props.space || store.space, q: query.value.trim() || undefined, include: props.modelValue || undefined }))
  if (mine !== asked) return
  loading.value = false
  rows.value = out?.rows || []
  for (const r of rows.value) known.value[r.value] = r
}
const searchSoon = useDebounceFn(search, 200)
watch(query, () => searchSoon())
watch(() => props.modelValue, (v) => { if (v && !known.value[v]) search() }, { immediate: true })

const shown = computed(() => known.value[props.modelValue]?.label || '')
const typed = computed(() => (query.value || '').trim())
const canAdd = computed(() => props.allowNew && typed.value && typed.value !== shown.value && !rows.value.some((r) => r.label.toLowerCase() === typed.value.toLowerCase()))
const items = computed(() => {
  const have = rows.value.some((r) => r.value === props.modelValue)
  const chosen = !have && known.value[props.modelValue] ? [known.value[props.modelValue]] : [] // the trigger takes its name from the options
  const list = [...rows.value, ...chosen].map((r) => ({ key: r.value, value: r.value, label: r.label, organisation: r.organisation, description: r.organisation || undefined }))
  if (canAdd.value) list.push({ type: 'custom', key: 'add', label: `Add '${typed.value}' as a person`, icon: 'lucide-user-plus', onClick: add, data: 'add' })
  return list
})
function choose(v) {
  emit('update:modelValue', v || '')
  if (v) emit('picked', known.value[v])
}
async function add() {
  const name = typed.value
  const out = await tryCall(() => itemData.tools.people_add({ name, space: props.space || store.space }))
  if (!out?.person) return
  known.value[out.person] = { value: out.person, label: out.name || name }
  toast.success(`Added ${out.name || name}.`)
  emit('added', out)
  choose(out.person)
}
</script>
