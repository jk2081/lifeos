<template>
  <ColumnSettings v-model="list.view.columns.shown.value" :doctype="list.doctype" :synthetic="list.synthetic" :hide-label="hideLabel"
    :can-reset="list.view.columns.isCustomized.value" @reset="list.view.columns.reset()" />
</template>
<script setup>
// Which columns the table view shows, their order and widths, with Reset. Wraps @framework/ui ColumnSettings.
import { ColumnSettings } from '@framework/ui/ColumnSettings'
defineProps({ list: { type: Object, required: true }, hideLabel: Boolean })
</script>
