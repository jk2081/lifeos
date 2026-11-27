<template>
  <OptionPicker :model-value="modelValue" :items="items" v-model:query="query" :shown="shown" :label="label" :placeholder="placeholder" :disabled="disabled" :clearable="clearable" prefix="area"
    search-placeholder="Search areas" empty-text="No area found" @update:model-value="(v) => emit('update:modelValue', v)" />
</template>
<script setup>
// The searchable area picker: the areas that are on, each part indented under its area, a search that matches any word of the name or its path.
// `extra` adds fixed choices before them ({ label: 'Unfiled', value: '' }). A thin wrapper on OptionPicker, as PersonPicker and GoalPicker are.
import { computed, ref } from 'vue'
import OptionPicker from './OptionPicker.vue'
import { areaOptions, loadLookups } from '@/lib/lookups'

const props = defineProps({ modelValue: { type: String, default: '' }, label: { type: String, default: '' }, placeholder: { type: String, default: 'Choose an area' },
  disabled: Boolean, clearable: { type: Boolean, default: true }, options: { type: Array, default: null } })
const emit = defineEmits(['update:modelValue'])
const query = ref('')
loadLookups()
const all = computed(() => props.options || areaOptions())
const words = computed(() => query.value.toLowerCase().split(/\s+/).filter(Boolean))
const items = computed(() => all.value.filter((o) => words.value.every((w) => (o.title || o.label).toLowerCase().includes(w))).map((o) => ({ value: o.value, label: o.label, description: o.title && o.title !== o.label.trim() ? o.title : undefined })))
const shown = computed(() => all.value.find((o) => o.value === props.modelValue)?.title || '')
</script>
