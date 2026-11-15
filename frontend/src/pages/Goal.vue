<template>
  <template v-if="d">
    <PageHead :title="d.goal.title" :crumb="{ to: '/journal/goals', label: 'Goals', here: d.cycle.title }"
      :sub="[d.goal.area_name, `${d.goal.actions.length} actions`, `${Math.round(d.goal.percent)}% of ticks done`].filter(Boolean).join(' · ')">
      <Badge :theme="d.goal.outcome === 'In Progress' ? 'blue' : 'gray'" :label="d.goal.outcome" />
      <Button label="Open grid" :route="`/journal?cycle=${d.cycle.name}`" />
    </PageHead>
    <div class="page-body"><div class="cols">
      <div class="half">
        <section><SectionHead>Actions</SectionHead>
          <Card flush><Row v-for="a in d.goal.actions" :key="a.name">
            <div class="min-w-0 flex-1"><div class="break-words text-base-medium" :class="a.status !== 'Open' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ a.title }}</div>
              <div class="text-sm text-ink-gray-6">{{ a.per_week }} a week · {{ Object.values(a.ticks).reduce((x, y) => x + y, 0) }} ticks so far</div></div>
            <Badge v-if="a.status !== 'Open'" :theme="a.status === 'Done' ? 'green' : 'gray'" :label="a.status" /></Row>
            <Empty v-if="!d.goal.actions.length" title="No actions." hint="Edit the goal on the grid to add weekly actions." /></Card>
        </section>
        <section v-if="d.goal.result_note"><SectionHead>Result</SectionHead><Card>{{ d.goal.result_note }}</Card></section>
        <section><SectionHead>Tasks for this goal</SectionHead>
          <Card flush><Row v-for="t in d.tasks" :key="t.name" :pane="'task:' + t.name" :label="t.title"><div class="min-w-0 flex-1">
            <div class="break-words text-base-medium text-ink-gray-9">{{ t.title }}</div><div class="text-sm text-ink-gray-6">{{ t.status }}{{ t.due_date ? ' · due ' + short(t.due_date) : '' }}</div></div></Row>
            <Empty v-if="!d.tasks.length" title="No tasks." hint="Link a task to this goal from the task's panel." /></Card>
        </section>
      </div>
      <div class="half">
        <section><SectionHead>History across cycles</SectionHead>
          <Card flush><Row v-for="h in d.history" :key="h.name" class="!items-center">
            <div class="min-w-0 flex-1"><RouterLink class="break-words text-base-medium hover:underline focus-visible:focus-ring" :class="h.name === d.goal.name ? 'text-ink-gray-9' : 'text-ink-blue-8'" :to="`/journal/goals/${h.name}`">{{ h.cycle_title }}</RouterLink>
              <div class="text-sm text-ink-gray-6">{{ h.cycle_status }}{{ h.result_note ? ' · ' + h.result_note : '' }}</div></div>
            <div class="w-24 shrink-0 max-md:w-12"><Progress size="sm" :value="Math.round(h.score)" /></div><span class="w-10 text-right tabular-nums">{{ Math.round(h.score) }}%</span>
            <Badge :label="h.outcome" /></Row></Card>
          <p class="mt-2 text-sm text-ink-gray-6">Every cycle this goal appeared in, followed through its carried-from links.</p>
        </section>
        <Backlinks doctype="Life Goal" :name="d.goal.name" />
      </div>
    </div></div>
  </template>
  <div v-else-if="missing" class="page-body"><Card><Empty title="This goal was not found." hint="It may belong to another space." /></Card></div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { Badge, Button, Progress } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import Backlinks from '@/components/Backlinks.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { api } from '@/lib/api'
import { short } from '@/lib/dates'

const props = defineProps({ id: String })
const d = ref(null)
const missing = ref(false)
onMounted(async () => {
  try {
    d.value = await api('journal.goal', { goal: props.id })
  } catch (e) {
    missing.value = true
  }
})
</script>
