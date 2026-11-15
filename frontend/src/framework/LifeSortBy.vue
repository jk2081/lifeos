<template>
  <SortBy v-model="list.view.sort.by.value" :doctype="list.doctype" :hide-label="hideLabel" />
</template>
<script setup>
// The sort control. Wraps @framework/ui SortBy.
import { SortBy } from '@framework/ui/SortBy'
defineProps({ list: { type: Object, required: true }, hideLabel: Boolean })
</script>
