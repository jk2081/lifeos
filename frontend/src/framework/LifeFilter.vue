<template>
  <Filter v-model="list.view.filters.conditions.value" :doctype="list.doctype" :fields="list.filterFields.value" :align="align" />
</template>
<script setup>
// The advanced filter: a popover of conditions on any field of the DocType. Wraps @framework/ui Filter.
import { Filter } from '@framework/ui/Filter'
defineProps({ list: { type: Object, required: true }, align: { type: String, default: 'start' } })
</script>
