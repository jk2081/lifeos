<template>
  <div class="flex flex-col gap-4" data-dashboard :data-view="view" :data-simple="d?.simple ? 1 : undefined">
    <template v-if="d">
      <!-- four cards: a number, what it is, and what it leads to. Two by two on a phone -->
      <div class="grid grid-cols-2 gap-3 md:gap-4" :class="d.cards.length === 3 ? 'md:grid-cols-3' : 'md:grid-cols-4'" data-dash-cards>
        <Stat v-for="c in d.cards" :key="c.key" tint :label="c.label" :value="c.value" :warn="c.tone === 'warn'" :open="c.open" class="min-w-0 !border-transparent max-md:!px-3 max-md:!py-2.5"
          data-dash-card :data-card="c.key" :data-open="c.open || undefined">
          <template v-if="c.parts.length || c.sub" #sub>
            <span v-if="c.parts.length" class="flex flex-wrap gap-x-2 text-sm">
              <Button v-for="p in c.parts" :key="p.text" class="relative !h-auto !px-0 !py-0 text-sm" :class="p.tone === 'warn' ? '!text-ink-amber-9' : p.tone === 'ok' ? '!text-ink-green-8' : '!text-ink-gray-6'" variant="ghost" :label="p.text"
                data-dash-part @click="openRef(p.open)" />
            </span>
            <template v-else>{{ c.sub }}</template>
          </template>
        </Stat>
      </div>

      <!-- two panels; they stack on a phone -->
      <div class="grid grid-cols-1 gap-3 md:gap-4" :class="d.panels.length === 2 && 'md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]'" data-dash-panels>
        <Card v-for="p in d.panels" :key="p.key" class="flex min-w-0 flex-col gap-1 !pb-2" data-dash-panel :data-panel="p.key">
          <SectionHead>{{ p.title }}</SectionHead>

          <!-- goals by area: each goal a bar -->
          <template v-if="p.kind === 'goals' && p.groups.length">
            <div v-for="g in p.groups" :key="g.area" class="flex flex-col" data-dash-group>
              <div v-if="p.groups.length > 1" class="pt-1 text-xs font-semibold uppercase tracking-wide text-ink-gray-6">{{ g.area }}</div>
              <Row v-for="r in g.rows" :key="r.ref" :pane="r.ref" :label="r.title" class="!block !py-1.5" data-dash-row :data-warn="r.tone === 'warn' || undefined">
                <div class="flex items-baseline justify-between gap-3"><span class="min-w-0 break-words text-base text-ink-gray-9">{{ r.title }}</span>
                  <span class="shrink-0 text-sm tabular-nums" :class="r.tone === 'warn' ? 'text-ink-amber-9' : 'text-ink-gray-6'">{{ r.sub }}</span></div>
                <Progress v-if="r.percent != null" class="mt-1.5" size="sm" :value="r.percent" :class="r.tone === 'warn' ? '[&>div>div]:!bg-surface-amber-7' : '[&>div>div]:!bg-surface-blue-7'" />
              </Row>
            </div>
          </template>

          <template v-else-if="p.rows.length">
            <Row v-for="(r, i) in p.rows" :key="(r.ref || '') + i" :pane="r.ref" :label="r.title" class="!block !py-2" data-dash-row :data-accent="r.accent || undefined">
              <div class="flex items-baseline justify-between gap-3">
                <span class="min-w-0 break-words text-base" :class="r.accent ? 'text-ink-blue-8' : r.done ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ r.title }}</span>
                <span class="shrink-0 text-sm tabular-nums" :class="r.tone === 'warn' ? 'text-ink-amber-9' : r.accent ? 'text-ink-blue-8' : 'text-ink-gray-6'">{{ r.sub }}</span>
              </div>
              <Progress v-if="r.percent != null && ['weeks', 'cycles', 'months'].includes(p.kind)" class="mt-1.5" size="sm" :value="Math.min(r.percent, 100)"
                :class="r.accent ? '[&>div>div]:!bg-surface-blue-7' : ''" />
            </Row>
            <div v-if="p.more" class="pt-1"><Button class="!px-0 !text-ink-blue-8" variant="ghost" :label="`${p.more.n} more`" data-dash-more @click="openRef(p.more.open)" /></div>
          </template>

          <EmptyState v-else-if="p.empty" :line="p.empty.line" :action="p.empty.action ? { label: p.empty.action, click: () => act(p.empty) } : null" data-dash-empty />

        </Card>
      </div>

      <!-- Week only: what the Brain did, every number a door -->
      <Card v-if="d.brain_line" class="flex flex-wrap items-center gap-x-1 gap-y-1 !py-3 text-base text-ink-gray-7" data-brain-line>
        <b class="mr-1 text-ink-gray-9">The Brain this week</b>
        <template v-for="(p, i) in d.brain_line.parts" :key="p.open">
          <span v-if="i" class="text-ink-gray-5" aria-hidden="true">·</span>
          <Button class="!h-auto !px-1 !py-0 !text-base !text-ink-gray-7" variant="ghost" :label="p.text" data-brain-part @click="openRef(p.open)" />
        </template>
      </Card>
    </template>
    <div v-else class="flex flex-col gap-3"><div class="grid grid-cols-2 gap-3 md:grid-cols-4"><Skeleton v-for="n in 4" :key="n" class="h-24 w-full" /></div><Skeleton class="h-48 w-full" /></div>
  </div>
</template>
<script setup>
import SectionHead from '@/components/ui/SectionHead.vue'
// The dashboard of a Today view (issue 123): four cards and two panels, and on Week one line about the Brain. One request (`dashboard.get`) loads a view. Every card, row and
// count opens in the side pane (a record, or `list:<kind>` for what a count counts); nothing here takes the person away from the page. With goals switched off the server sends
// other cards in their place, so this component draws whatever it is given.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, Progress, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Stat from '@/components/ui/Stat.vue'
import Row from '@/components/ui/Row.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { todayData } from '@/data/today'
import { openChat } from '@/lib/ask'
import { tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { onRecordChanged, openRef } from '@/lib/pane'

const props = defineProps({ view: String })
const emit = defineEmits(['loaded'])
const route = useRoute()
const router = useRouter()
const d = ref(null)
let seq = 0
async function load() {
  const mine = ++seq
  const res = await tryCall(() => todayData.dashboard.get({ view: props.view, date: route.query.date || undefined, space: store.space }))
  if (res && mine === seq) { d.value = res; emit('loaded', res) }
}
watch(() => [props.view, route.query.date, store.space], load)
onRecordChanged(load)
onMounted(load)

// an empty card's one action: Chat, or a screen
function act(e) {
  if (e.to === 'chat') openChat()
  else if (e.to) router.push(e.to)
}
defineExpose({ reload: load, data: computed(() => d.value) })
</script>
