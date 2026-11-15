<template>
  <template v-if="d">
    <div class="flex flex-wrap items-center gap-2"><Badge :theme="d.goal.outcome === 'In Progress' ? 'blue' : 'gray'" :label="d.goal.outcome" />
      <span class="text-sm text-ink-gray-6">{{ d.cycle.title }} · {{ Math.round(d.goal.percent) }}% of ticks done</span></div>
    <section><SectionHead>Actions</SectionHead>
      <Card flush><Row v-for="a in d.goal.actions" :key="a.name">
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium" :class="a.status !== 'Open' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ a.title }}</div>
          <div class="text-sm text-ink-gray-6">{{ a.per_week }} a week · {{ Object.values(a.ticks).reduce((x, y) => x + y, 0) }} ticks so far</div></div>
        <Badge v-if="a.status !== 'Open'" :theme="a.status === 'Done' ? 'green' : 'gray'" :label="a.status" /></Row>
        <Empty v-if="!d.goal.actions.length" title="No actions." hint="Edit the goal on the grid to add weekly actions." /></Card>
    </section>
    <section v-if="d.goal.result_note"><SectionHead>Result</SectionHead><Card class="text-base text-ink-gray-8">{{ d.goal.result_note }}</Card></section>
    <section v-if="d.tasks.length"><SectionHead>Tasks for this goal</SectionHead>
      <Card flush><Row v-for="t in d.tasks" :key="t.name" :pane="'task:' + t.name" :label="t.title"><div class="min-w-0 flex-1">
        <div class="break-words text-base-medium text-ink-gray-9">{{ t.title }}</div><div class="text-sm text-ink-gray-6">{{ t.status }}{{ t.due_date ? ' · due ' + short(t.due_date) : '' }}</div></div></Row></Card>
    </section>
    <section v-if="d.history.length > 1"><SectionHead>History across cycles</SectionHead>
      <Card flush><Row v-for="h in d.history" :key="h.name" class="!items-center" :pane="h.name !== d.goal.name ? 'goal:' + h.name : null" :label="h.cycle_title">
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ h.cycle_title }}</div><div class="text-sm text-ink-gray-6">{{ h.cycle_status }}{{ h.result_note ? ' · ' + h.result_note : '' }}</div></div>
        <span class="w-10 text-right tabular-nums text-ink-gray-8">{{ Math.round(h.score) }}%</span><Badge :label="h.outcome" /></Row></Card>
    </section>
    <Backlinks doctype="Life Goal" :name="d.goal.name" />
  </template>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { Badge } from 'frappe-ui'
import Card from '../ui/Card.vue'
import Row from '../ui/Row.vue'
import SectionHead from '../ui/SectionHead.vue'
import Empty from '../Empty.vue'
import Backlinks from '../Backlinks.vue'
import { api } from '@/lib/api'
import { short } from '@/lib/dates'

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
