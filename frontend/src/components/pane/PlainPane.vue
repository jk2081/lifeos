<template>
  <template v-if="d">
    <template v-if="type === 'checkin'">
      <Card flush>
        <Row v-for="s in d.scores" :key="s.name"><span class="min-w-0 flex-1 text-base text-ink-gray-8">{{ dimension(s.dimension) }}</span>
          <span class="text-sm text-ink-gray-6">habits {{ range(s.habits_low, s.habits_high) }} · situation {{ range(s.situation_low, s.situation_high) }}</span></Row>
        <Empty v-if="!d.scores.length" title="No scores." hint="This check-in has a reflection only." />
      </Card>
      <section v-if="d.reflection_md"><SectionHead>Reflection</SectionHead><Card><Md :text="d.reflection_md" /></Card></section>
    </template>
    <template v-else>
      <section><SectionHead>Goals for the month</SectionHead>
        <Card flush><Row v-for="g in d.goals" :key="g.name"><div class="min-w-0 flex-1"><div class="break-words text-base-medium" :class="g.status === 'Done' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ g.title }}</div></div>
          <Badge v-if="g.priority" :label="g.priority" /><Badge v-if="g.status && g.status !== 'Open'" :theme="g.status === 'Done' ? 'green' : 'amber'" :label="g.status" /></Row>
          <Empty v-if="!d.goals.length" title="No goals." hint="Add goals for the month in the Journal." /></Card></section>
      <section v-if="d.mindsweep_md"><SectionHead>Mindsweep</SectionHead><Card><Md :text="d.mindsweep_md" /></Card></section>
    </template>
  </template>
</template>
<script setup>
// Check-ins and month plans are worked on in the Journal. The pane shows them read-only, with Open full page.
import { onMounted, ref } from 'vue'
import { Badge } from 'frappe-ui'
import Card from '../ui/Card.vue'
import Row from '../ui/Row.vue'
import SectionHead from '../ui/SectionHead.vue'
import Md from '../Md.vue'
import Empty from '../Empty.vue'
import { db } from '@/lib/api'
import { MONTHS, long } from '@/lib/dates'
import { loadLookups, lookups } from '@/lib/lookups'

const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const d = ref(null)
const range = (lo, hi) => (lo == null ? '—' : lo === hi ? String(lo) : `${lo}-${hi}`)
const dimension = (id) => (lookups.dimensions || []).find((x) => x.name === id)?.dimension_name || id
onMounted(async () => {
  try {
    await loadLookups()
    const doc = await db.get(props.type === 'checkin' ? 'Life Check-in' : 'Life Month Plan', props.name)
    doc.scores = doc.scores || []
    doc.goals = doc.goals || []
    d.value = doc
    emit('meta', props.type === 'checkin' ? { title: `Check-in, ${long(doc.date, true)}`, fullPage: '/today/month?view=checkins' }
      : { title: `Month plan, ${MONTHS[doc.month - 1]} ${doc.year}`, fullPage: '/today/month' })
  } catch (e) {
    emit('missing')
  }
})
</script>
