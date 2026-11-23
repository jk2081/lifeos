<template>
  <!-- no calendar: one line instead of the strip -->
  <p v-if="!strip" class="text-sm text-ink-gray-7" data-calendar-strip-none>Connect Google Calendar to see last week's meetings here ·
    <RouterLink class="text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="{ path: '/settings', query: { tab: 'calendar' } }">Settings › Calendar</RouterLink></p>
  <template v-else>
    <!-- desktop: the period's days side by side; meetings that matter are white cards with a mark, others grey and smaller -->
    <div class="grid overflow-hidden rounded-5 border border-outline-gray-2 max-md:hidden" :style="{ gridTemplateColumns: `repeat(${Math.min(strip.days.length, 7)}, minmax(0, 1fr))` }"
      data-calendar-strip>
      <div v-for="d in shownDays" :key="d.date" class="flex min-w-0 flex-col gap-1 border-r border-outline-gray-1 p-2 last:border-r-0" :data-strip-day="d.date">
        <div class="text-sm text-ink-gray-7">{{ d.label }}</div>
        <template v-for="e in ordered(d.events).slice(0, PER_DAY)" :key="e.name">
          <Button v-if="e.matters" variant="outline" size="sm" class="w-full min-w-0 !justify-start" :class="e.name === open && '!border-outline-gray-9'"
            :label="e.title" :data-strip-meeting="e.name" :data-mark="e.mark" @click="emit('open', e.name)">
            <template #prefix>
              <span v-if="e.mark === 'linked'" class="size-2 flex-none rounded-full bg-surface-green-7" role="img" aria-label="Something linked" />
              <span v-else class="size-2 flex-none rounded-full border-2 border-outline-amber-6" role="img" aria-label="Nothing captured" />
            </template>
            <span class="truncate">{{ e.title }}</span>
          </Button>
          <!-- other events are grey and smaller; opening one lets the owner mark it as mattering -->
          <Button v-else variant="subtle" size="sm" class="!h-6 w-full min-w-0 !justify-start !text-xs !text-ink-gray-7" :label="e.title" :title="e.title"
            data-strip-event :data-strip-other="e.name" @click="emit('open', e.name)"><span class="truncate">{{ e.title }}</span></Button>
        </template>
        <Button v-if="d.events.length > PER_DAY" variant="ghost" size="sm" class="!justify-start" :label="`+ ${d.events.length - PER_DAY} more`" @click="emit('list')" />
      </div>
    </div>
    <!-- phone: the meetings that matter as a list grouped by day -->
    <div class="flex flex-col gap-2 md:hidden" data-calendar-list>
      <p v-if="!strip.matters.length" class="text-sm text-ink-gray-6">No meetings that matter in this period.</p>
      <div v-for="d in strip.days.filter((x) => x.events.some((e) => e.matters))" :key="d.date">
        <div class="text-sm-medium text-ink-gray-7">{{ d.label }}</div>
        <Button v-for="e in d.events.filter((x) => x.matters)" :key="e.name" class="mt-1 w-full !justify-start" :label="e.title" :data-strip-meeting="e.name" :data-mark="e.mark"
          @click="emit('open', e.name)">
          <template #prefix><span class="size-2 flex-none rounded-full" :class="e.mark === 'linked' ? 'bg-surface-green-7' : 'border-2 border-outline-amber-6'" aria-hidden="true" /></template>
        </Button>
      </div>
    </div>
  </template>
</template>
<script setup>
// Last week's calendar strip (board 28). A long review period shows its last seven days here; every meeting is in the list.
import { computed } from 'vue'
import { Button } from 'frappe-ui'

const PER_DAY = 3
const props = defineProps({ strip: Object, open: String })
const emit = defineEmits(['open', 'list'])
const shownDays = computed(() => props.strip.days.slice(-7))
// meetings that matter first, then the rest, each by time
const ordered = (events) => [...events].sort((a, b) => (b.matters - a.matters) || String(a.start).localeCompare(String(b.start)))
</script>
