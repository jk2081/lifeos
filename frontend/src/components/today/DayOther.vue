<template>
  <PageHead :title="`${weekday(date)}, ${long(date, true)}`" :sub="sub">
    <Button icon="lucide-chevron-left" label="Previous day" tooltip="Previous day" data-cal-prev @click="go(addDays(date, -1))" />
    <Button label="Today" data-cal-today @click="go(store.today)" />
    <Button icon="lucide-chevron-right" label="Next day" tooltip="Next day" data-cal-next @click="go(addDays(date, 1))" />
  </PageHead>
  <div class="page-body" data-day-other :data-date="date">
    <section>
      <SectionHead>{{ date < store.today ? 'That day' : 'This day' }}</SectionHead>
      <Card flush>
        <Row v-for="(it, i) in items" :key="i" :pane="itemRef(it)" :label="itemLabel(it)" class="!items-center" data-day-item :data-source="it.source">
          <span class="w-14 flex-none text-sm tabular-nums text-ink-gray-6">{{ it.all_day ? 'All day' : time(it.start) }}</span>
          <span class="min-w-0 flex-1 break-words rounded px-1.5 py-0.5 text-base" :class="chipClass(it)">{{ itemLabel(it) }}</span>
          <span class="text-sm text-ink-gray-6 max-md:hidden">{{ SOURCE[chipType(it)] }}</span>
        </Row>
        <Empty v-if="data && !items.length" title="Nothing on this day." hint="Events, tasks planned at a time, tasks due and key dates show here." />
      </Card>
    </section>
  </div>
</template>
<script setup>
// Today > Day for another date (issue 16): Week and Month open a day here. Today's own Day (the plate) is Today.vue; for any other date
// this lists what the calendar holds that day. `date=` is in the URL; Today returns to the plate.
import { computed } from 'vue'

import { Button } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { store } from '@/lib/store'
import { chipClass, chipType, itemLabel, itemRef, openDay, useCalendarRange } from '@/lib/calRange'
import { addDays, long, time, weekday } from '@/lib/dates'

const props = defineProps({ date: String })
const SOURCE = { event: 'Meeting', trip: 'Trip', planned: 'Planned', due: 'Due', important: 'Key date', vault: 'Document expires' }
const { data, itemsOn } = useCalendarRange(computed(() => [props.date, props.date]))
const items = computed(() => itemsOn(props.date))
const sub = computed(() => (data.value ? `${items.value.length} thing${items.value.length === 1 ? '' : 's'}` : ' '))
const go = (d) => openDay(d)
</script>
