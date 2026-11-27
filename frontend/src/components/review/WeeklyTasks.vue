<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-tasks>
    <div class="page-body !gap-4">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 class="text-xl-semibold text-ink-gray-9">Your commitments</h2>
          <p class="text-sm text-ink-gray-6">What left your plate this week, then the tasks nobody has touched for a while.</p>
        </div>
        <Stat v-if="s" class="w-64 max-md:w-full !border-0 !bg-transparent !p-0" label="Left to decide" :value="s.left" :sub="`${s.decided} decided in this review`" data-left-to-clear :data-n="s.left" />
      </div>
      <section v-if="p" class="flex flex-col gap-2" data-left-your-plate>
        <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <SectionHead>Left your plate · {{ p.out.n }}</SectionHead>
          <span class="text-sm text-ink-gray-6">this period · <CountLink :count="p.in" data-door="review-plate-in" /> came in, <CountLink :count="p.out" /> went out</span>
          <RouterLink class="ml-auto text-base text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="p.outbox" data-open-outbox>Open the Outbox</RouterLink>
        </div>
        <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat v-for="x in p.piles" :key="x.pile" :label="x.pile" :sub="x.line" :data-plate-pile="x.pile">
            <CountLink :count="x" :count-key="'plate-' + x.pile" :data-door="'review-plate-' + x.pile" />
          </Stat>
        </div>
      </section>
      <!-- issue 118: the waiting pile, never on Today, looked at here: by person, oldest first -->
      <section class="flex flex-col gap-2" data-waiting-on-others>
        <SectionHead>Waiting on others<template v-if="w"> · <span class="tabular-nums" data-waiting-total>{{ w.total }}</span></template></SectionHead>
        <template v-if="w && w.groups.length">
          <Card v-for="g in w.groups" :key="g.who" flush data-waiting-group :data-who="g.who">
            <div class="border-b border-outline-gray-1 px-4 py-2 text-sm-medium text-ink-gray-7">{{ g.who }} · {{ g.rows.length }}</div>
            <Row bare v-for="t in g.rows" :key="t.name" class="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3" data-waiting-task :data-task="t.name" :data-past="t.past ? '' : undefined">
              <div class="min-w-0 flex-1 basis-60">
                <RouterLink class="break-words text-base-medium text-ink-gray-9 hover:underline focus-visible:focus-ring" :to="{ query: { ...route.query, open: 'task:' + t.name } }">{{ t.title }}</RouterLink>
                <div class="text-sm text-ink-gray-6">since {{ t.since }}<template v-if="t.from"> · from {{ t.from }}</template><template v-if="t.check_by"> · <span :class="t.past ? 'text-ink-amber-9' : ''" data-check-by>check by {{ t.check_by }}</span></template></div>
              </div>
              <div class="flex gap-2">
                <Button label="Done" :disabled="r.readOnly || busy === t.name" data-waiting-done @click="change(t, 'done')" />
                <Dropdown :options="menu(t)" placement="right"><Button label="Change" :disabled="r.readOnly || busy === t.name" data-waiting-change /></Dropdown>
              </div>
            </Row>
          </Card>
        </template>
        <Card v-else-if="w"><EmptyState line="Nothing is waiting on anyone. Asks the Brain finds in your mail that someone else is on wait here, and come back to you in this review." /></Card>
        <Skeleton v-else class="h-16 w-full" />
        <div v-if="w && w.closed.length" class="mt-2 flex flex-col gap-1.5" data-closed-by-itself>
          <h4 class="text-sm-medium text-ink-gray-7">Closed by itself this week · {{ w.closed.length }}</h4>
          <Card flush>
            <Row bare v-for="c in w.closed" :key="c.name" class="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2.5" data-closed-task :data-task="c.name">
              <div class="min-w-0 flex-1 basis-60 break-words text-base text-ink-gray-9">{{ c.title }}<span class="text-sm text-ink-gray-6"> · done {{ c.completed_on }}</span></div>
              <Button label="Change" :disabled="r.readOnly || busy === c.name" data-closed-change @click="reopen(c)" />
            </Row>
          </Card>
        </div>
      </section>
      <section class="flex flex-col gap-2" data-stale-tasks>
        <SectionHead>Stale tasks</SectionHead>
        <Card v-if="s && s.tasks.length" flush>
          <Row bare v-for="t in s.tasks" :key="t.name" class="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3" data-stale-task :data-task="t.name">
            <div class="min-w-0 flex-1 basis-60">
              <RouterLink class="break-words text-base-medium text-ink-gray-9 hover:underline focus-visible:focus-ring" :to="{ query: { ...route.query, open: 'task:' + t.name } }">{{ t.title }}</RouterLink>
              <div class="text-sm text-ink-gray-6">{{ [t.area_name, t.status === 'Waiting' ? 'waiting' + (t.waiting_on ? ' on ' + t.waiting_on : '') : '', `untouched ${t.age} days`].filter(Boolean).join(' · ') }}</div>
            </div>
            <div class="flex gap-2" role="group" :aria-label="`What to do with ${t.title}`">
              <Button v-for="b in BUTTONS" :key="b.decision" :label="b.label" :disabled="r.readOnly || busy === t.name" :data-stale-decision="b.decision" @click="settle(t, b.decision)" />
            </div>
          </Row>
        </Card>
        <Card v-else-if="s"><EmptyState line="No stale tasks. Open tasks nobody has touched for a month show here, each with Keep, Someday and Drop." /></Card>
        <Skeleton v-else class="h-24 w-full" />
      </section>
    </div>
    <ReviewFooter back label="Next: Goals" :disabled="!r.head.done.tasks" :line="line" @back="emit('go', 'library')" @next="emit('go', 'goals')" />
  </div>
</template>
<script setup>
import Row from '@/components/ui/Row.vue'
import Stat from '@/components/ui/Stat.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
// Tab 2, Tasks: Left your plate (the Outbox for the period, read only), Waiting on others (issue 118), then one list of the stale tasks, each with Keep,
// Someday and Drop (issue 72). Next: Goals opens once no stale task is left to decide.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button, Dropdown, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import CountLink from '@/components/ui/CountLink.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ReviewFooter from '@/components/review/ReviewFooter.vue'
import { useReview } from '@/lib/review'
import { nudge as nudgeTask } from '@/lib/handoff'

const emit = defineEmits(['go'])
const r = useReview()
const s = ref(null)
const p = ref(null)
const w = ref(null)
const route = useRoute()
const busy = ref('')
const BUTTONS = [{ label: 'Keep', decision: 'keep' }, { label: 'Someday', decision: 'someday' }, { label: 'Drop', decision: 'drop' }]
const line = computed(() => {
  if (r.head.done.tasks) return 'Every stale task is decided'
  return s.value ? `Opens when every stale task is decided · ${s.value.left} left` : ''
})
async function load() {
  const [plate, stale, waiting] = await Promise.all([r.read('plate'), r.read('stale_tasks'), r.read('waiting')])
  p.value = plate
  s.value = stale
  w.value = waiting
}
// Done, Move to my plate, Still waiting (check-by a week on), Nudge (a two-line follow-up as a draft or a WhatsApp link; nothing is sent) and Not needed
const menu = (t) => [{ label: 'Move to my plate', onClick: () => change(t, 'plate') }, { label: 'Still waiting', onClick: () => change(t, 'still') },
  { label: 'Nudge', onClick: () => nudge(t) }, { label: 'Not needed', onClick: () => change(t, 'not_needed') }]
async function change(t, to) {
  busy.value = t.name
  try { await r.act('waiting_change', { task: t.name, to }) } finally { busy.value = '' }
}
async function reopen(c) {
  busy.value = c.name
  try { await r.act('closed_change', { task: c.name }) } finally { busy.value = '' }
}
async function nudge(t) {
  await nudgeTask(t.name)  // a draft or the WhatsApp link, opened on the task; nothing is sent
}
async function settle(t, decision) {
  busy.value = t.name
  try {
    const out = await r.act('settle_stale', { task: t.name, decision })
    s.value = out.stale
  } finally { busy.value = '' }
}
watch(() => r.version, load)
onMounted(load)
</script>
