<template>
  <template v-if="d">
    <template v-if="type === 'checkin'">
      <div class="cd list">
        <div v-for="s in d.scores" :key="s.name" class="rw"><span class="grow">{{ dimension(s.dimension) }}</span>
          <span class="mt">habits {{ range(s.habits_low, s.habits_high) }} · situation {{ range(s.situation_low, s.situation_high) }}</span></div>
        <Empty v-if="!d.scores.length" title="No scores." hint="This check-in has a reflection only." />
      </div>
      <section v-if="d.reflection_md"><h2 class="sh">Reflection</h2><div class="cd"><Md :text="d.reflection_md" /></div></section>
    </template>
    <template v-else>
      <section><h2 class="sh">Goals for the month</h2>
        <div class="cd list"><div v-for="g in d.goals" :key="g.name" class="rw"><div class="grow"><div class="ttl" :style="g.status === 'Done' ? 'text-decoration: line-through; color: var(--mut)' : ''">{{ g.title }}</div></div>
          <span v-if="g.priority" class="pl n">{{ g.priority }}</span><span v-if="g.status && g.status !== 'Open'" class="pl" :class="g.status === 'Done' ? 'g' : 'o'">{{ g.status }}</span></div>
          <Empty v-if="!d.goals.length" title="No goals." hint="Add goals for the month in the Journal." /></div></section>
      <section v-if="d.mindsweep_md"><h2 class="sh">Mindsweep</h2><div class="cd"><Md :text="d.mindsweep_md" /></div></section>
    </template>
  </template>
</template>
<script setup>
// Check-ins and month plans are worked on in the Journal. The pane shows them read-only, with Open full page.
import { onMounted, ref } from 'vue'
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
    emit('meta', props.type === 'checkin' ? { title: `Check-in, ${long(doc.date, true)}`, fullPage: '/journal/checkins' }
      : { title: `Month plan, ${MONTHS[doc.month - 1]} ${doc.year}`, fullPage: '/journal/month' })
  } catch (e) {
    emit('missing')
  }
})
</script>
