<template>
  <div v-if="goal.children?.length || goal.no_twelve_week" class="mt-1 flex flex-col gap-1 pl-4 md:pl-8" data-goal-breakdown>
    <ul v-if="goal.children?.length" class="flex flex-col gap-1">
      <li v-for="c in goal.children" :key="c.name" data-goal-child :data-goal="c.name">
        <Card class="relative flex flex-wrap items-center gap-x-3 gap-y-1 py-2 hover:bg-surface-gray-1">
          <RefLink class="absolute inset-0 rounded-5 focus-visible:focus-ring" :to="`goal:${c.name}`" :aria-label="`Open ${c.title}`" data-goal-open />
          <span class="min-w-0 flex-1 break-words text-base-medium text-ink-gray-9" data-goal-title>{{ c.title }}</span>
          <Badge v-if="c.week" theme="blue" :label="`Week ${c.week} · ${Math.round(c.score ?? 0)}%`" data-goal-score />
          <span class="text-sm tabular-nums text-ink-gray-7">{{ c.progress.label }}</span>
        </Card>
      </li>
    </ul>
    <div v-else class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-6" data-no-twelve-week>
      <span>no 12-week goal yet</span>
      <Button v-if="writable" size="sm" variant="subtle" label="Break it down" :aria-label="`Break down ${goal.title} into a 12-week goal`" data-break-down @click="emit('break', goal)" />
    </div>
  </div>
</template>
<script setup>
// Goals > By area, This cycle: the 12-week goals that serve a Year goal, indented under it; a Year goal with none says so and offers
// Break it down, which starts a 12-week goal that serves it (issue 137).
import { Badge, Button } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import RefLink from '@/components/ui/RefLink.vue'

defineProps({ goal: { type: Object, required: true }, writable: Boolean })
const emit = defineEmits(['break'])
</script>
