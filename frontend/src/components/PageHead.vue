<template>
  <PageHeader class="!min-h-0 !items-stretch py-3 md:py-4" data-page-head>
    <div class="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div class="min-w-0">
        <Breadcrumbs v-if="crumb" class="-ml-1 mb-0.5" :items="[{ label: crumb.label, route: crumb.to }, { label: crumb.here }]" />
        <h1 class="flex items-center gap-2">
          <PageHeaderTitle class="!text-xl">{{ title }}</PageHeaderTitle>
          <Badge v-if="count !== null && count !== undefined" size="lg" :label="count" data-lv-count :aria-label="`${count} matching`" />
        </h1>
        <div v-if="sub || $slots.sub" class="mt-0.5 text-sm text-ink-gray-6"><slot name="sub">{{ sub }}</slot></div>
      </div>
      <div class="flex flex-wrap items-center gap-2"><slot /><AskBox v-if="!store.isAgent" /></div>
    </div>
  </PageHeader>
</template>
<script setup>
// The header of a screen: frappe-ui's PageHeader with its title, Breadcrumbs for a parent screen, the count of what a list
// matches, a line of context, and the screen's actions.
import { Badge, Breadcrumbs, PageHeader, PageHeaderTitle } from 'frappe-ui'
import AskBox from './ask/AskBox.vue'
import { store } from '@/lib/store'
defineProps({ title: String, sub: String, crumb: Object, count: { type: Number, default: null } })
</script>
