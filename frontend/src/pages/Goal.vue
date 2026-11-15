<template>
  <template v-if="d">
    <PageHead :title="d.goal.title" :crumb="{ to: '/journal/goals', label: 'Goals', here: d.cycle.title }"
      :sub="[d.goal.area_name, `${d.goal.actions.length} actions`, `${Math.round(d.goal.percent)}% of ticks done`].filter(Boolean).join(' · ')">
      <span class="pl" :class="d.goal.outcome === 'In Progress' ? 'b' : 'n'">{{ d.goal.outcome }}</span>
      <RouterLink class="bt s" :to="`/journal?cycle=${d.cycle.name}`">Open grid</RouterLink>
    </PageHead>
    <div class="bd"><div class="cols">
      <div class="half">
        <section><h2 class="sh">Actions</h2>
          <div class="cd list"><div v-for="a in d.goal.actions" :key="a.name" class="rw">
            <div class="grow"><div class="ttl" :style="a.status !== 'Open' ? 'text-decoration: line-through; color: var(--mut)' : ''">{{ a.title }}</div>
              <div class="mt">{{ a.per_week }} a week · {{ Object.values(a.ticks).reduce((x, y) => x + y, 0) }} ticks so far</div></div>
            <span v-if="a.status !== 'Open'" class="pl" :class="a.status === 'Done' ? 'g' : 'n'">{{ a.status }}</span></div>
            <Empty v-if="!d.goal.actions.length" title="No actions." hint="Edit the goal on the grid to add weekly actions." /></div>
        </section>
        <section v-if="d.goal.result_note"><h2 class="sh">Result</h2><div class="cd">{{ d.goal.result_note }}</div></section>
        <section><h2 class="sh">Tasks for this goal</h2>
          <div class="cd list"><div v-for="t in d.tasks" :key="t.name" class="rw rowlink" :data-ref="'task:' + t.name" @click="openRef('task:' + t.name)"><div class="grow">
            <div class="ttl">{{ t.title }}</div><div class="mt">{{ t.status }}{{ t.due_date ? ' · due ' + short(t.due_date) : '' }}</div></div></div>
            <Empty v-if="!d.tasks.length" title="No tasks." hint="Link a task to this goal from the task's panel." /></div>
        </section>
      </div>
      <div class="half">
        <section><h2 class="sh">History across cycles</h2>
          <div class="cd list"><div v-for="h in d.history" :key="h.name" class="rw" style="align-items: center">
            <div class="grow"><RouterLink class="ttl" :to="`/journal/goals/${h.name}`" :style="h.name === d.goal.name ? 'color: var(--ink)' : ''">{{ h.cycle_title }}</RouterLink>
              <div class="mt">{{ h.cycle_status }}{{ h.result_note ? ' · ' + h.result_note : '' }}</div></div>
            <div class="br" style="max-width: 120px"><i :style="`width: ${h.score}%`"></i></div><span style="width: 40px; text-align: right">{{ Math.round(h.score) }}%</span>
            <span class="pl n">{{ h.outcome }}</span></div></div>
          <p class="mt" style="margin: 8px 0 0">Every cycle this goal appeared in, followed through its carried-from links.</p>
        </section>
        <Backlinks doctype="Life Goal" :name="d.goal.name" />
      </div>
    </div></div>
  </template>
  <div v-else-if="missing" class="bd"><div class="cd"><Empty title="This goal was not found." hint="It may belong to another space." /></div></div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import Backlinks from '@/components/Backlinks.vue'
import { api } from '@/lib/api'
import { short } from '@/lib/dates'
import { openRef } from '@/lib/pane'

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
