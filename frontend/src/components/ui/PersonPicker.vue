<template>
  <div class="flex min-w-0 flex-col gap-1.5" data-person-picker>
    <div v-if="label" class="text-sm text-ink-gray-6">{{ label }}</div>
    <div class="flex items-center gap-1">
      <Combobox v-if="wide" class="min-w-0 flex-1" trigger="button" :model-value="modelValue || null" :options="items" :filterable="false" :loading="loading" :disabled="disabled"
        :placeholder="placeholder" empty-text="No one found" v-model:query="query" data-person-combobox @update:model-value="choose" @update:open="(v) => v && (query = '', search())">
      </Combobox>
      <Button v-else class="min-w-0 flex-1 justify-between" variant="outline" :disabled="disabled" :label="shown || placeholder" icon-right="lucide-chevron-down" data-person-open @click="sheet = true" />
      <Button v-if="modelValue && !disabled" variant="ghost" size="sm" icon="lucide-x" label="Clear" data-person-clear @click="emit('update:modelValue', '')" />
    </div>
    <Dialog v-model:open="sheet" :title="label || 'Choose a person'" size="sm" data-person-sheet>
      <div class="flex flex-col gap-2">
        <TextInput v-model="query" autofocus type="search" placeholder="Search by name, company or email" data-person-search />
        <div class="max-h-[50vh] overflow-y-auto" data-person-list>
          <button v-for="o in items" :key="o.key" type="button" class="flex w-full min-w-0 flex-col rounded px-2 py-2 text-left hover:bg-surface-gray-2" :data-person-option="o.value || 'add'" @click="o.onClick ? o.onClick() : choose(o.value)">
            <span class="truncate text-base text-ink-gray-8">{{ o.label }}</span>
            <span v-if="o.organisation" class="truncate text-sm text-ink-gray-5">{{ o.organisation }}</span>
          </button>
          <p v-if="!items.length && !loading" class="px-2 py-3 text-sm text-ink-gray-6">No one found.</p>
        </div>
      </div>
    </Dialog>
  </div>
</template>
<script setup>
// One searchable person picker (issue 136): people only, each with their company under the name, a search that also matches the company and the email, and the
// server answering as you type so no one is out of reach. At the end, "Add 'x' as a person" when nothing matches exactly. On a phone it opens as a sheet.
import { computed, ref, watch } from 'vue'
import { Button, Combobox, Dialog, TextInput, toast } from 'frappe-ui'
import { useDebounceFn, useMediaQuery } from '@vueuse/core'
import { tryCall } from '@/lib/api'
import { itemData } from '@/data/item'
import { store } from '@/lib/store'

const props = defineProps({ modelValue: { type: String, default: '' }, space: { type: String, default: '' }, label: { type: String, default: '' }, placeholder: { type: String, default: 'Choose a person' },
  disabled: Boolean, allowNew: { type: Boolean, default: true } })
const emit = defineEmits(['update:modelValue', 'added', 'picked'])
const wide = useMediaQuery('(min-width: 768px)')
const sheet = ref(false)
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
watch(sheet, (on) => { if (on) { query.value = ''; search() } })
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
  sheet.value = false
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
