<template>
  <Card flush data-inventory>
    <div class="overflow-x-auto">
      <table class="w-full min-w-[30rem] text-base">
        <thead><tr class="border-b border-outline-gray-1 text-sm text-ink-gray-6">
          <th class="py-2.5 pr-2 text-left font-normal">Untouched for</th>
          <th v-for="c in inv.columns" :key="c.key" class="px-2 py-2.5 text-right font-normal">{{ c.label }}</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in inv.rows" :key="r.key" class="border-b border-outline-gray-1 last:border-b-0" :data-inv-row="r.key">
            <td class="py-2.5 pr-2 text-ink-gray-8">{{ r.label }}</td>
            <td v-for="c in inv.columns" :key="c.key" class="px-2 py-2.5 text-right"
              :class="[hot(r, c.key) && 'bg-surface-amber-1', c.key === 'total' && 'font-semibold']" :data-inv-cell="r.key + ':' + c.key">
              <CountLink :count="r.cells[c.key]" :tone="hot(r, c.key) ? 'text-ink-amber-9 font-semibold' : c.key === 'total' ? 'text-ink-gray-9' : 'text-ink-gray-8'"
                :aria-label="`${r.cells[c.key].n} ${r.label.toLowerCase()}, ${c.label.toLowerCase()}`" :count-key="`inventory:${r.key}:${c.key}`" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </Card>
</template>
<script setup>
// Reset's Inventory: rows by kind, columns by time untouched. A cell past the stuck threshold with something in it is
// highlighted. Every number opens exactly those items.
import Card from '../ui/Card.vue'
import CountLink from '../ui/CountLink.vue'
const props = defineProps({ inv: Object })
const OLD = { under_30: 0, '30_90': 30, '90_180': 90, over_180: 180 }
const hot = (r, key) => key !== 'total' && r.key !== 'notes' && OLD[key] >= (props.inv.stuck_after_days || 30) && r.cells[key].n > 0
</script>
