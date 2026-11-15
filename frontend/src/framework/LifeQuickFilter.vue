<template>
  <QuickFilter v-model:filters="list.view.filters.conditions.value" v-model:fields="list.view.quickFilter.fields.value"
    v-model:customizing="list.view.quickFilter.customizing.value" :doctype="list.doctype" />
</template>
<script setup>
// The always-visible strip of one-tap filters. It edits the same conditions as LifeFilter. Wraps @framework/ui QuickFilter.
import { QuickFilter } from '@framework/ui/QuickFilter'
defineProps({ list: { type: Object, required: true } })
</script>
