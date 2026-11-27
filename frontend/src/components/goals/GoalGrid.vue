<template>
  <div class="flex flex-col gap-3" data-goal-grid :data-all="all ? 1 : 0">
    <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm text-ink-gray-6" data-goal-grid-scores>
      <span v-if="cur" data-grid-week-score><b class="text-base-medium text-ink-gray-9">Week {{ cur }}</b> <span class="tabular-nums" data-grid-week-percent>{{ pct(weeks[cur - 1].percent) }}</span> so far</span>
      <span v-else-if="closed">Cycle closed</span>
      <span v-else>Not running</span>
      <span class="tabular-nums" data-grid-cycle-score>Cycle <b class="text-base-medium text-ink-gray-9">{{ pct(average) }}</b> · target {{ target }}%</span>
    </div>
    <div v-if="actions.length" class="flex flex-col" role="table" aria-label="Weekly actions" data-grid-table>
      <div class="grid items-center gap-x-1 border-b border-outline-gray-1 pb-1.5 text-xs text-ink-gray-6" :style="cols" role="row">
        <span role="columnheader">Action</span>
        <span v-for="w in shown" :key="w" class="text-center tabular-nums" :class="w === cur ? 'rounded-4 bg-surface-gray-2 py-0.5 text-ink-gray-9 font-medium' : ''" role="columnheader"
          :data-grid-head="w" :data-now="w === cur ? 1 : 0">W{{ w }}</span>
      </div>
      <Row bare v-for="a in actions" :key="a.name" class="grid items-center gap-x-1 py-1.5" :style="cols" role="row" data-grid-action :data-action="a.name">
        <div class="relative min-w-0 cursor-pointer pr-2" role="rowheader">
          <button type="button" class="absolute inset-0 focus-visible:focus-ring" :aria-label="`Open ${a.title}'s goal`" :data-ref="'goal:' + goal.name" data-action-open @click="openRef('goal:' + goal.name)" />
          <div class="truncate text-base" :class="a.status !== 'Open' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'" :title="a.title">{{ a.title }}</div>
          <div class="text-xs text-ink-gray-6" data-action-line>{{ a.per_week }} a week · {{ plural(total(a), 'tick') }} so far<template v-if="a.status !== 'Open'"> · {{ a.status }}</template></div>
        </div>
        <template v-for="w in shown" :key="w">
          <button v-if="w === cur && a.status === 'Open' && canTick" type="button" role="cell"
            class="mx-auto flex h-8 w-full max-w-10 items-center justify-center rounded-4 border text-xs tabular-nums focus-visible:focus-ring"
            :class="n(a, w) ? 'border-outline-gray-9 bg-surface-gray-9 text-surface-base' : 'border-outline-gray-3 bg-surface-base text-ink-gray-6'"
            :aria-label="`${a.title}, week ${w}: ${n(a, w)} of ${a.per_week}. Tap to tick`" data-grid-cell data-tickable :data-week="w" :data-count="n(a, w)" @click="tap(a, w)">{{ a.per_week > 1 ? `${n(a, w)}/${a.per_week}` : n(a, w) ? '✓' : '' }}</button>
          <span v-else role="cell" class="mx-auto flex h-8 w-full max-w-10 items-center justify-center rounded-4 text-xs tabular-nums"
            :class="[n(a, w) >= a.per_week ? 'bg-surface-gray-9 text-surface-base' : n(a, w) ? 'bg-surface-gray-4 text-ink-gray-9' : w > (cur || 12) || !cur ? 'bg-surface-gray-1' : 'bg-surface-gray-2', w === cur ? 'ring-1 ring-outline-gray-4' : '']"
            data-grid-cell :data-week="w" :data-count="n(a, w)">{{ n(a, w) ? (a.per_week > 1 ? `${n(a, w)}/${a.per_week}` : '✓') : '' }}</span>
        </template>
      </Row>
    </div>
    <EmptyState v-else line="No actions yet. Use Edit to add the weekly actions. Each week you tick what you did." :action="canEdit ? { label: 'Edit', click: () => emit('edit') } : null" />
    <div v-if="!all && actions.length" class="md:hidden"><Button variant="ghost" class="!text-ink-blue-8" label="All 12 weeks" data-grid-all @click="open = true" /></div>
    <Dialog v-if="!all" v-model:open="open" title="All 12 weeks" size="lg">
      <GoalGrid all :goal="goal" :weeks="weeks" :current-week="cur" :average="average" :target="target" :closed="closed" :can-edit="canEdit" @changed="emit('changed')" />
    </Dialog>
  </div>
</template>
<script setup>
import Row from '@/components/ui/Row.vue'
// A 12 Week Year goal's own grid, on its page: its actions as rows, the 12 weeks as columns, this week highlighted and the only
// one that can be ticked. A tick is the same record as on Goals > Cycles. On a phone it shows this week and the two before it;
// "All 12 weeks" opens the whole grid in a sheet.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import EmptyState from '@/components/ui/EmptyState.vue'
import { goalsData } from '@/data/goals'
import { openRef } from '@/lib/pane'
import { errorText } from '@/lib/api'
import { plural } from '@/lib/plural'
import { toast } from 'frappe-ui'

// the goal as goals.detail gives it (its actions with ticks per week), and the cycle's scores
const props = defineProps({ goal: { type: Object, required: true }, weeks: { type: Array, required: true }, currentWeek: Number, average: Number, target: Number,
  closed: Boolean, canEdit: Boolean, all: Boolean })
const emit = defineEmits(['changed', 'edit'])
const open = ref(false)
const phone = ref(false)
let query = null
const sync = () => { phone.value = query.matches }
onMounted(() => { query = window.matchMedia('(max-width: 767px)'); sync(); query.addEventListener('change', sync) })
onBeforeUnmount(() => query?.removeEventListener('change', sync))

const cur = computed(() => props.currentWeek || null)
const actions = computed(() => props.goal.actions)
const canTick = computed(() => props.canEdit && !!cur.value)
// the weeks shown: all twelve, or on a phone this week and the two before it (the first three before the cycle runs)
const shown = computed(() => {
  const all = Array.from({ length: 12 }, (_, i) => i + 1)
  if (props.all || !phone.value) return all
  const last = Math.min(Math.max(cur.value || (props.closed ? 12 : 3), 3), 12)
  return all.slice(last - 3, last)
})
const cols = computed(() => ({ gridTemplateColumns: `minmax(0, ${props.all ? 1.6 : 2.4}fr) repeat(${shown.value.length}, minmax(0, 1fr))` }))
const pct = (v) => Math.round(v || 0) + '%'
const n = (a, w) => a.ticks[String(w)] || 0
const total = (a) => Object.values(a.ticks).reduce((x, y) => x + y, 0)

async function tap(a, w) {
  const before = n(a, w)
  const next = before >= a.per_week ? 0 : before + 1
  a.ticks[String(w)] = next
  try {
    await goalsData.goals.tick({ action: a.name, week: w, count: next })
    emit('changed')
  } catch (e) {
    a.ticks[String(w)] = before
    toast.error(errorText(e))
  }
}
</script>
