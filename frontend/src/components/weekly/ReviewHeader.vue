<template>
  <PageHeader class="!min-h-0 py-3" data-review-head>
    <div class="flex w-full min-w-0 flex-col">
    <div class="flex w-full min-w-0 flex-wrap items-center gap-x-6 gap-y-2">
      <div class="min-w-0 md:w-[240px]">
        <h1 class="text-base-medium text-ink-gray-9" data-review-title>{{ title }}</h1>
        <div class="text-sm text-ink-gray-6" data-review-period>{{ h.period_text }}</div>
      </div>
      <!-- desktop: numbered tabs, ticked when done (board 28) -->
      <Tabs class="max-md:hidden" :model-value="tab" @update:model-value="(v) => emit('go', v)">
        <TabList aria-label="Review steps">
          <TabTrigger v-for="t in tabs" :key="t.value" :value="t.value" :label="t.label" :title="`About ${h.tab_minutes[t.value]} minutes`"
            :data-review-tab-btn="t.value" :data-done="h.done[t.value] ? 1 : 0" :data-openable="h.openable[t.value] ? 1 : 0">
            <template #prefix>
              <span v-if="h.done[t.value] && t.value !== tab" class="flex size-5 items-center justify-center rounded-full bg-surface-green-7 text-ink-base"
                role="img" aria-label="done"><span class="lucide-check size-3.5" aria-hidden="true" /></span>
              <span v-else class="flex size-5 items-center justify-center rounded-full text-xs tabular-nums"
                :class="t.value === tab ? 'bg-surface-gray-9 text-ink-base' : 'bg-surface-gray-2 text-ink-gray-7'">{{ t.n }}</span>
            </template>
          </TabTrigger>
        </TabList>
      </Tabs>
      <div class="ml-auto flex items-center gap-3">
        <span class="text-sm text-ink-gray-6 max-lg:hidden" data-review-estimate>About {{ h.minutes }} minutes · {{ r.readOnly ? 'read only' : (r.saving === 'Saving…' ? 'saving…' : 'saved as you go') }}</span>
        <Button variant="ghost" label="Pause" data-review-pause @click="emit('pause')" />
      </div>
    </div>
    <!-- phone: a step bar, "Step 2 of 4 · Tasks", four segments with ticks on the done ones -->
    <div class="mt-2 md:hidden" data-review-stepbar>
      <div class="mb-1.5 text-sm text-ink-gray-7">Step {{ cur.n }} of {{ tabs.length }} · {{ cur.label }}</div>
      <div class="grid grid-cols-4 gap-1.5">
        <Button v-for="t in tabs" :key="t.value" size="sm" :variant="t.value === tab ? 'solid' : 'subtle'" :label="`${t.n} ${t.label}`"
          :aria-label="`Step ${t.n}, ${t.label}${h.done[t.value] ? ', done' : ''}`" :data-review-step="t.value" @click="emit('go', t.value)">
          <span v-if="h.done[t.value] && t.value !== tab" class="lucide-check size-4" aria-hidden="true" />
          <span v-else class="tabular-nums">{{ t.n }}</span>
        </Button>
      </div>
    </div>
    </div>
  </PageHeader>
</template>
<script setup>
// The review's header: title and period, the four numbered tabs (a step bar on a phone), the estimate, and Pause.
import { computed } from 'vue'
import { Button, PageHeader, TabList, Tabs, TabTrigger } from 'frappe-ui'
import { TABS, useReview } from '@/lib/review'

// the weekly review's tabs and title unless the monthly or 12-week review passes its own
const props = defineProps({ tab: String, tabs: { type: Array, default: () => TABS }, title: { type: String, default: 'Weekly review' } })
const emit = defineEmits(['go', 'pause'])
const r = useReview()
const h = computed(() => r.head)
const cur = computed(() => props.tabs.find((t) => t.value === props.tab) || props.tabs[0])
</script>
