<template>
  <Link v-model="model" :doctype="doctype" :filters="filters" :label="label" :placeholder="placeholder" :disabled="disabled" :title="title" :required="required" />
</template>
<script setup>
// A picker for a Link field: area, project, person, goal, space. It searches with Frappe's own link search,
// so the space rules apply, and `filters` narrows it to the current space. Wraps @framework/ui Link.
import { Link } from '@framework/ui/components/Link/index.ts'
const model = defineModel({ type: [String, null], default: null })
defineProps({ doctype: { type: String, required: true }, filters: { type: Object, default: undefined }, label: String, placeholder: String,
  disabled: Boolean, required: Boolean, title: String })
</script>
