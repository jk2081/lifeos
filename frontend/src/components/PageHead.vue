<template>
  <PageHeader class="!min-h-0 !items-stretch py-3 md:py-4" data-page-head>
    <div class="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div class="min-w-0">
        <!-- the space (two or more spaces only), then the parent screen if there is one -->
        <Breadcrumbs v-if="crumbs.length" class="-ml-1 mb-0.5 max-md:hidden" :items="crumbs" data-lens-crumb />
        <h1 class="flex flex-wrap items-center gap-2">
          <PageHeaderTitle class="!text-xl">{{ title }}</PageHeaderTitle>
          <Badge v-if="count !== null && count !== undefined" size="lg" :label="count" data-lv-count :aria-label="`${count} matching`" />
          <!-- the page's `?area=` as a removable chip, so a narrowed view is always plain -->
          <Button v-if="store.lensArea" size="sm" variant="subtle" :label="lensAreaName" icon-right="lucide-x" :aria-label="`Narrowed to ${lensAreaName}. Show all of life`"
            :tooltip="'Show all of life'" data-lens-chip @click="clearArea">
            <template #prefix><span class="size-2 rounded-full" :class="dotClass(lensArea)" aria-hidden="true" /></template>
          </Button>
        </h1>
        <div v-if="sub || $slots.sub" class="mt-0.5 text-sm text-ink-gray-6"><slot name="sub">{{ sub }}</slot></div>
      </div>
      <div class="flex flex-wrap items-center gap-2"><slot /><AskBox v-if="!store.isAgent" /></div>
    </div>
  </PageHeader>
  <!-- a place's tabs (Plan, Library) under the header of whichever screen is open in it -->
  <TabBar v-if="place" class="flex-none border-b border-outline-gray-1" inset :tabs="place.tabs" :model-value="place.current" :label="place.label" data-place-tabs
    @update:model-value="place.set" />
</template>
<script setup>
// The header of a screen: frappe-ui's PageHeader with the space (two or more spaces) and any parent screen as Breadcrumbs, its title, the page's
// area as a removable chip, the count of what a list matches, a line of context, and the screen's actions.
import { computed, inject } from 'vue'
import { Badge, Breadcrumbs, Button, PageHeader, PageHeaderTitle } from 'frappe-ui'
import AskBox from './ask/AskBox.vue'
import TabBar from './TabBar.vue'
import { store } from '@/lib/store'
import { clearArea, dotClass, lensArea, lensAreaName, manySpaces } from '@/lib/lens'
const props = defineProps({ title: String, sub: String, crumb: Object, count: { type: Number, default: null } })
// Plan and Library provide their tabs ({ tabs, current, set, label }); any screen open in them shows the tabs under its header
const placeTabs = inject('placeTabs', null)
const place = computed(() => (placeTabs ? placeTabs.value : null))
const crumbs = computed(() => [
  ...(manySpaces.value ? [{ label: store.space }] : []),
  ...(props.crumb ? [{ label: props.crumb.label, route: props.crumb.to }, { label: props.crumb.here }] : []),
])
</script>
