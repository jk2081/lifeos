<template>
  <PageHeader class="!min-h-0 !items-stretch py-3 md:py-4" data-page-head>
    <div class="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div class="min-w-0">
        <!-- the lens as a breadcrumb (UX fixes, set 6): "Private · All of life", then the parent screen if there is one -->
        <Breadcrumbs class="-ml-1 mb-0.5 max-md:hidden" :items="crumbs" data-lens-crumb />
        <h1 class="flex flex-wrap items-center gap-2">
          <PageHeaderTitle class="!text-xl">{{ title }}</PageHeaderTitle>
          <Badge v-if="count !== null && count !== undefined" size="lg" :label="count" data-lv-count :aria-label="`${count} matching`" />
          <!-- the lens's area as a removable chip, so a narrowed view is always plain -->
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
</template>
<script setup>
// The header of a screen: frappe-ui's PageHeader with the lens and any parent screen as Breadcrumbs, its title, the lens's
// area as a removable chip, the count of what a list matches, a line of context, and the screen's actions.
import { computed } from 'vue'
import { Badge, Breadcrumbs, Button, PageHeader, PageHeaderTitle } from 'frappe-ui'
import AskBox from './ask/AskBox.vue'
import { store } from '@/lib/store'
import { clearArea, dotClass, lensArea, lensAreaName } from '@/lib/lens'
const props = defineProps({ title: String, sub: String, crumb: Object, count: { type: Number, default: null } })
const crumbs = computed(() => [
  { label: `${store.space || 'No space'} · ${lensAreaName.value}` },
  ...(props.crumb ? [{ label: props.crumb.label, route: props.crumb.to }, { label: props.crumb.here }] : []),
])
</script>
