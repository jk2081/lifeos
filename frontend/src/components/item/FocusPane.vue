<template>
  <div class="flex flex-col gap-4" data-focus-pane>
    <template v-if="d">
      <Card data-pane-focus-standard>
        <div class="mb-1 text-sm text-ink-gray-6">Standard: what good looks like, kept up over time</div>
        <p v-if="d.standard" class="text-base text-ink-gray-9">{{ d.standard }}</p>
        <p v-else class="text-sm text-ink-gray-6">No standard yet. It is written on the focus's full page.</p>
      </Card>
      <section data-pane-focus-principles>
        <SectionHead>Principles</SectionHead>
        <Card>
          <ol v-if="d.principles.length" class="flex flex-col">
            <li v-for="(p, i) in d.principles" :key="i" class="flex items-baseline gap-3 border-b border-outline-gray-1 py-2 last:border-b-0">
              <span class="w-5 flex-none rounded-4 bg-surface-gray-2 text-center text-xs tabular-nums text-ink-gray-6">{{ i + 1 }}</span>
              <span class="min-w-0 break-words text-base text-ink-gray-9">{{ p }}</span>
            </li>
          </ol>
          <p v-else class="text-sm text-ink-gray-6">No principles yet. Short lines on how to work, in order.</p>
        </Card>
      </section>
      <section data-pane-focus-goals>
        <SectionHead>Goals serving this focus</SectionHead>
        <Card flush class="!px-4">
          <Row v-for="g in rows" :key="g.name" :pane="'goal:' + g.name" :label="g.title" class="!items-center" :class="g.finished && 'opacity-60'">
            <span class="w-24 flex-none rounded-4 bg-surface-gray-2 px-2 py-0.5 text-xs text-ink-gray-7">{{ g.tag }}</span>
            <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ g.title }}</span>
            <span class="flex-none text-sm tabular-nums text-ink-gray-7">{{ g.finished ? g.outcome : g.progress.label }}</span>
          </Row>
          <Empty v-if="!rows.length" title="No goals yet." hint="An annual goal says what this focus is for this year." />
        </Card>
      </section>
      <Card data-pane-focus-review>
        <div class="text-sm-medium text-ink-gray-9">In the 12-week review</div>
        <p class="mt-1 text-sm text-ink-gray-6">Each focus gets one question: set a goal this cycle, or just maintain it. A goal in {{ d.going.cycles_with_goal }} of the last {{ d.going.cycles_considered || 3 }} cycles.</p>
      </Card>
    </template>
    <div v-else-if="!failed" class="flex flex-col gap-2"><Skeleton class="h-16 w-full" /><Skeleton class="h-12 w-full" /></div>
  </div>
</template>
<script setup>
// A focus in the Drawer (issue 128): its standard, principles, goals and review cadence. Editing stays on the full page.
import { computed, onMounted, ref } from 'vue'
import { Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import { tryCall } from '@/lib/api'
import { todayData } from '@/data/today'

const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const d = ref(null)
const failed = ref(false)
const rows = computed(() => [
  ...d.value.annual.map((g) => ({ ...g, tag: 'Annual' })),
  ...d.value.cycle.map((g) => ({ ...g, tag: '12 Week Year' })),
  ...d.value.other.map((g) => ({ ...g, tag: g.horizon === 'Long term' ? 'Open' : g.horizon })),
  ...d.value.finished.map((g) => ({ ...g, tag: 'Done', finished: true })),
])
onMounted(async () => {
  d.value = await tryCall(() => todayData.focus.get({ area: props.name }))
  if (!d.value) { failed.value = true; return emit('missing') }
  emit('meta', { title: d.value.title, kind: 'Focus', sub: [d.value.life_area?.area_name, d.value.part?.area_name].filter(Boolean).join(' · '), fullPage: `/focus/${props.name}` })
})
</script>
