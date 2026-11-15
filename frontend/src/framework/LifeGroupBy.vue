<template>
  <GroupBy v-model="list.view.groupBy.value" :doctype="list.doctype" :exclude="exclude" :hide-label="hideLabel" />
</template>
<script setup>
// The group-by control: one summary row per value of the chosen fields. Wraps @framework/ui GroupBy.
import { GroupBy } from '@framework/ui/GroupBy'
defineProps({ list: { type: Object, required: true }, hideLabel: Boolean, exclude: { type: Array, default: () => ['space'] } })
</script>
