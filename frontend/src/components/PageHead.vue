<template>
  <PageHeader class="!min-h-0 !items-stretch py-3 md:py-4" data-page-head>
    <div class="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div class="min-w-0">
        <!-- issue 83: the path above the title, each ancestor a link, the title last; a back button goes to the parent in the path -->
        <div v-if="crumbs.length" class="mb-0.5 flex min-w-0 items-center gap-1" data-page-path-row>
          <Button class="-ml-1.5 shrink-0" variant="ghost" size="sm" icon="lucide-arrow-left" label="Back" :tooltip="`Back to ${parent.label}`" :route="parent.to" data-page-back />
          <Breadcrumbs class="min-w-0 [&_a]:!text-sm [&_button]:!text-sm" :items="crumbs" data-page-path />
        </div>
        <h1 class="flex flex-wrap items-center gap-2">
          <PageHeaderTitle class="!text-xl" data-page-title>{{ title }}</PageHeaderTitle>
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
  <div v-if="place" class="flex flex-none items-center justify-between border-b border-outline-gray-1 max-md:flex-col max-md:items-stretch">
    <TabBar class="min-w-0 flex-1 max-md:w-full" inset :tabs="place.tabs" :model-value="place.current" :label="place.label" data-place-tabs @update:model-value="place.set" />
    <component :is="place.end" v-if="place.end" />
  </div>
</template>
<script setup>
// The header of a screen: frappe-ui's PageHeader with the path (issue 83) as Breadcrumbs and a back button, its title, the page's
// area as a removable chip, the count of what a list matches, a line of context, and the screen's actions.
import { computed, inject, watchEffect } from 'vue'
import { Badge, Breadcrumbs, Button, PageHeader, PageHeaderTitle } from 'frappe-ui'
import AskBox from './ask/AskBox.vue'
import TabBar from './TabBar.vue'
import { store } from '@/lib/store'
import { clearArea, dotClass, lensArea, lensAreaName } from '@/lib/lens'
import { tabTitle, trailOf } from '@/lib/trail'
// `path` is the page's ancestors, place first ({ label, to }); a page below a place gives it, a place's own page does not (lib/trail.js)
const props = defineProps({ title: String, sub: String, path: Array, count: { type: Number, default: null } })
// Plan and Library provide their tabs ({ tabs, current, set, label }); any screen open in them shows the tabs under its header
const placeTabs = inject('placeTabs', null)
const place = computed(() => (placeTabs ? placeTabs.value : null))
const crumbs = computed(() => (props.path?.length ? trailOf(props.path, props.title || '').map((p) => (p.to ? { label: p.label, route: p.to } : p)) : []))
const parent = computed(() => props.path[props.path.length - 1])
// the browser tab's title is the path in reverse; a place's own page is its title
watchEffect(() => { if (props.title) document.title = tabTitle(props.title, props.path) })
</script>
