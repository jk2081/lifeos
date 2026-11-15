<template>
  <!-- One row. On a phone it scrolls sideways inside itself and the open tab is brought into view. -->
  <div ref="el" class="scroll-x" data-tab-bar :data-tab-current="modelValue">
    <Tabs :model-value="modelValue" @update:model-value="pick">
      <TabList class="min-w-max" :class="inset ? 'px-4 md:px-7' : ''" :aria-label="label">
        <TabTrigger v-for="t in tabs" :key="t.value" class="max-md:min-h-11" :value="t.value" :label="t.label" :data-tab="t.value">
          <template v-if="t.count !== undefined && t.count !== null" #suffix>
            <span class="text-sm tabular-nums text-ink-gray-6" data-tab-count :aria-label="`${t.count} ${t.noun || 'records'}`">{{ t.count }}</span>
          </template>
        </TabTrigger>
      </TabList>
    </Tabs>
  </div>
</template>
<script setup>
// The tab bar of the app, in all three patterns: tabs on a record or page (`tab=`), tabs in the record pane (`ptab=`)
// and a list's state tabs. It is frappe-ui's Tabs with a count after each label. The arrow keys come from the
// component; [ and ] move to the previous and next tab from anywhere on the page (lib/tabs.js).
import { nextTick, onMounted, ref, watch } from 'vue'
import { TabList, Tabs, TabTrigger } from 'frappe-ui'
import { useTabKeys } from '@/lib/tabs'

const props = defineProps({
  tabs: { type: Array, required: true }, // [{ value, label, count }]: a count shows as a quiet number, 0 included
  modelValue: { type: [String, Number], default: undefined },
  label: { type: String, default: 'Tabs' }, // the accessible name of the row
  level: { type: Number, default: 1 }, // 1 on a page, 2 in the record pane: [ and ] go to the highest on screen
  inset: Boolean, // the page's side padding, for a bar that sits outside .page-body
})
const emit = defineEmits(['update:modelValue'])
const el = ref(null)
const pick = (v) => { if (v !== props.modelValue) emit('update:modelValue', v) }
function step(direction) {
  const i = props.tabs.findIndex((t) => t.value === props.modelValue)
  const next = props.tabs[i + direction]
  if (i >= 0 && next) pick(next.value)
}
useTabKeys({ get level() { return props.level }, step })
async function reveal() {
  await nextTick()
  const row = el.value
  const tab = row?.querySelector('[data-state="active"]')
  if (!row || !tab) return
  // scroll only the row, never the page
  const a = tab.getBoundingClientRect()
  const b = row.getBoundingClientRect()
  if (a.left < b.left) row.scrollLeft += a.left - b.left - 16
  else if (a.right > b.right) row.scrollLeft += a.right - b.right + 16
}
// again when the counts arrive: they widen the tabs
watch(() => [props.modelValue, props.tabs.map((t) => `${t.value}:${t.count}`).join()], reveal)
onMounted(reveal)
</script>
