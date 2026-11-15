<template>
  <template v-if="d">
    <div class="chips"><span class="pl" :class="d.goal.outcome === 'In Progress' ? 'b' : 'n'">{{ d.goal.outcome }}</span>
      <span class="mt">{{ d.cycle.title }} · {{ Math.round(d.goal.percent) }}% of ticks done</span></div>
    <section><h2 class="sh">Actions</h2>
      <div class="cd list"><div v-for="a in d.goal.actions" :key="a.name" class="rw">
        <div class="grow"><div class="ttl" :style="a.status !== 'Open' ? 'text-decoration: line-through; color: var(--mut)' : ''">{{ a.title }}</div>
          <div class="mt">{{ a.per_week }} a week · {{ Object.values(a.ticks).reduce((x, y) => x + y, 0) }} ticks so far</div></div>
        <span v-if="a.status !== 'Open'" class="pl" :class="a.status === 'Done' ? 'g' : 'n'">{{ a.status }}</span></div>
        <Empty v-if="!d.goal.actions.length" title="No actions." hint="Edit the goal on the grid to add weekly actions." /></div>
    </section>
    <section v-if="d.goal.result_note"><h2 class="sh">Result</h2><div class="cd">{{ d.goal.result_note }}</div></section>
    <section v-if="d.tasks.length"><h2 class="sh">Tasks for this goal</h2>
      <div class="cd list"><div v-for="t in d.tasks" :key="t.name" class="rw rowlink" @click="openRef('task:' + t.name)"><div class="grow">
        <div class="ttl">{{ t.title }}</div><div class="mt">{{ t.status }}{{ t.due_date ? ' · due ' + short(t.due_date) : '' }}</div></div></div></div>
    </section>
    <section v-if="d.history.length > 1"><h2 class="sh">History across cycles</h2>
      <div class="cd list"><div v-for="h in d.history" :key="h.name" class="rw" :class="{ rowlink: h.name !== d.goal.name }" style="align-items: center" @click="h.name !== d.goal.name && openRef('goal:' + h.name)">
        <div class="grow"><div class="ttl">{{ h.cycle_title }}</div><div class="mt">{{ h.cycle_status }}{{ h.result_note ? ' · ' + h.result_note : '' }}</div></div>
        <span style="width: 40px; text-align: right">{{ Math.round(h.score) }}%</span><span class="pl n">{{ h.outcome }}</span></div></div>
    </section>
    <Backlinks doctype="Life Goal" :name="d.goal.name" />
  </template>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import Empty from '../Empty.vue'
import Backlinks from '../Backlinks.vue'
import { api } from '@/lib/api'
import { short } from '@/lib/dates'
import { openRef } from '@/lib/pane'

const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const d = ref(null)
onMounted(async () => {
  try {
    d.value = await api('journal.goal', { goal: props.name })
    const g = d.value.goal
    emit('meta', { title: g.title, area: g.area, area_name: g.area_name, project: g.project, fullPage: `/journal/goals/${g.name}`,
      sub: `${g.actions.length} action${g.actions.length === 1 ? '' : 's'}` })
  } catch (e) {
    emit('missing')
  }
})
</script>
