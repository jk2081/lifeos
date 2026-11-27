<template>
  <div class="flex min-w-0 flex-col gap-1.5" :data-picker="prefix" v-bind="mark('picker')">
    <div v-if="label" class="text-sm text-ink-gray-6">{{ label }}</div>
    <div class="flex items-center gap-1">
      <Combobox v-if="wide" class="min-w-0 flex-1" trigger="button" :model-value="modelValue || null" :options="items" :filterable="false" :loading="loading" :disabled="disabled"
        :placeholder="placeholder" :empty-text="emptyText" :query="query" v-bind="mark('combobox')" @update:query="(v) => emit('update:query', v)" @update:model-value="choose"
        @update:open="(v) => v && (emit('update:query', ''), emit('open'))">
      </Combobox>
      <Button v-else class="min-w-0 flex-1 justify-between" variant="outline" :disabled="disabled" :label="shown || placeholder" icon-right="lucide-chevron-down" v-bind="mark('open')" @click="open" />
      <Button v-if="modelValue && !disabled && clearable" variant="ghost" size="sm" icon="lucide-x" label="Clear" v-bind="mark('clear')" @click="emit('update:modelValue', '')" />
    </div>
    <Dialog v-model:open="sheet" :title="label || placeholder" size="sm" v-bind="mark('sheet')">
      <div class="flex flex-col gap-2">
        <TextInput :model-value="query" autofocus type="search" :placeholder="searchPlaceholder" v-bind="mark('search')" @update:model-value="(v) => emit('update:query', v)" />
        <div class="max-h-[50vh] overflow-y-auto" role="listbox" v-bind="mark('list')">
          <button v-for="o in items" :key="o.key ?? o.value" type="button" role="option" :aria-selected="o.value === modelValue" class="flex w-full min-w-0 flex-col rounded px-2 py-2 text-left hover:bg-surface-gray-2" :data-option="o.value || 'add'"
            v-bind="mark('option', o.value || 'add')" @click="o.onClick ? ((sheet = false), o.onClick()) : choose(o.value)">
            <span class="truncate text-base text-ink-gray-8">{{ o.label.trim() }}</span>
            <span v-if="o.description" class="truncate text-sm text-ink-gray-6">{{ o.description }}</span>
          </button>
          <p v-if="!items.length && !loading" class="px-2 py-3 text-sm text-ink-gray-6">{{ emptyText }}.</p>
        </div>
      </div>
    </Dialog>
  </div>
</template>
<script setup>
// The base of every searchable picker (people, areas, goals): one way to show an option, a searchable list in a popover on a wide screen and a
// sheet with the search focused on a phone. It owns no data: the wrapper (PersonPicker, AreaPicker, GoalPicker) gives it `items` already narrowed by
// `query`, and hears the typing through update:query. An item is { value, label, description? }, or { type: 'custom', key, label, icon, onClick } for an action.
// `prefix` names the data attributes (data-<prefix>-open, -search, -option and the like) so each picker keeps its own.
import { ref, watch } from 'vue'
import { Button, Combobox, Dialog, TextInput } from 'frappe-ui'
import { useMediaQuery } from '@vueuse/core'

const props = defineProps({ modelValue: { type: String, default: '' }, items: { type: Array, default: () => [] }, query: { type: String, default: '' }, shown: { type: String, default: '' },
  label: { type: String, default: '' }, placeholder: { type: String, default: 'Choose' }, searchPlaceholder: { type: String, default: 'Search' }, emptyText: { type: String, default: 'Nothing found' },
  prefix: { type: String, default: 'option' }, loading: Boolean, disabled: Boolean, clearable: { type: Boolean, default: true } })
const emit = defineEmits(['update:modelValue', 'update:query', 'open', 'picked'])
const wide = useMediaQuery('(min-width: 768px)')
const sheet = ref(false)
const mark = (part, value) => ({ [`data-${props.prefix}-${part}`]: value ?? '' })
function open() { sheet.value = true }
watch(sheet, (on) => { if (on) { emit('update:query', ''); emit('open') } })
function choose(v) {
  sheet.value = false
  emit('update:modelValue', v || '')
  if (v) emit('picked', v)
}
defineExpose({ choose })
</script>
