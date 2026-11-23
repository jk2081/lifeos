<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-tasks>
    <div class="page-body !gap-4">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 class="text-xl-semibold text-ink-gray-9">Your commitments</h2>
          <p class="text-sm text-ink-gray-6">What left your plate this week, then the tasks nobody has touched for a while.</p>
        </div>
        <div v-if="s" class="w-64 max-md:w-full" data-left-to-clear :data-n="s.left">
          <div class="flex items-baseline justify-end gap-2 max-md:justify-start"><span class="text-3xl-semibold tabular-nums text-ink-gray-9">{{ s.left }}</span>
            <span class="text-sm text-ink-gray-7">left to decide</span></div>
          <div class="mt-0.5 text-right text-sm text-ink-gray-6 max-md:text-left">{{ s.decided }} decided in this review</div>
        </div>
      </div>
      <section v-if="p" class="flex flex-col gap-2" data-left-your-plate>
        <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 class="text-base-medium text-ink-gray-9">Left your plate · {{ p.out.n }}</h3>
          <span class="text-sm text-ink-gray-6">this period · <CountLink :count="p.in" data-door="review-plate-in" /> came in, <CountLink :count="p.out" /> went out</span>
          <RouterLink class="ml-auto text-base text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="p.outbox" data-open-outbox>Open the Outbox</RouterLink>
        </div>
        <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Card v-for="x in p.piles" :key="x.pile" class="flex flex-col" :data-plate-pile="x.pile">
            <span class="text-sm text-ink-gray-7">{{ x.pile }}</span>
            <CountLink class="text-xl-semibold" :count="x" :count-key="'plate-' + x.pile" :data-door="'review-plate-' + x.pile" />
            <span class="text-sm text-ink-gray-6">{{ x.line }}</span>
          </Card>
        </div>
      </section>
      <section class="flex flex-col gap-2" data-stale-tasks>
        <h3 class="text-base-medium text-ink-gray-9">Stale tasks</h3>
        <Card v-if="s && s.tasks.length" flush>
          <div v-for="t in s.tasks" :key="t.name" class="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-outline-gray-1 px-4 py-3 last:border-b-0" data-stale-task :data-task="t.name">
            <div class="min-w-0 flex-1 basis-60">
              <RouterLink class="break-words text-base-medium text-ink-gray-9 hover:underline focus-visible:focus-ring" :to="{ query: { ...route.query, open: 'task:' + t.name } }">{{ t.title }}</RouterLink>
              <div class="text-sm text-ink-gray-6">{{ [t.area_name, t.status === 'Waiting' ? 'waiting' + (t.waiting_on ? ' on ' + t.waiting_on : '') : '', `untouched ${t.age} days`].filter(Boolean).join(' · ') }}</div>
            </div>
            <div class="flex gap-2" role="group" :aria-label="`What to do with ${t.title}`">
              <Button v-for="b in BUTTONS" :key="b.decision" :label="b.label" :disabled="r.readOnly || busy === t.name" :data-stale-decision="b.decision" @click="settle(t, b.decision)" />
            </div>
          </div>
        </Card>
        <Card v-else-if="s"><Empty title="No stale tasks." hint="Open tasks nobody has touched for a month show here, each with Keep, Someday and Drop." /></Card>
        <Skeleton v-else class="h-24 w-full" />
      </section>
    </div>
    <ReviewFooter back label="Next: Goals" :disabled="!r.head.done.tasks" :line="line" @back="emit('go', 'library')" @next="emit('go', 'goals')" />
  </div>
</template>
<script setup>
// Tab 2, Tasks: Left your plate (the Outbox for the period, read only), then one list of the stale tasks, each with Keep,
// Someday and Drop (issue 72). Next: Goals opens once no stale task is left to decide.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import CountLink from '@/components/ui/CountLink.vue'
import Empty from '@/components/Empty.vue'
import ReviewFooter from './ReviewFooter.vue'
import { useReview } from '@/lib/review'

const emit = defineEmits(['go'])
const r = useReview()
const s = ref(null)
const p = ref(null)
const route = useRoute()
const busy = ref('')
const BUTTONS = [{ label: 'Keep', decision: 'keep' }, { label: 'Someday', decision: 'someday' }, { label: 'Drop', decision: 'drop' }]
const line = computed(() => {
  if (r.head.done.tasks) return 'Every stale task is decided'
  return s.value ? `Opens when every stale task is decided · ${s.value.left} left` : ''
})
async function load() {
  const [plate, stale] = await Promise.all([r.read('plate'), r.read('stale_tasks')])
  p.value = plate
  s.value = stale
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
