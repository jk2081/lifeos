<template>
  <RouterLink v-if="count" :to="count.to" class="rounded-1 tabular-nums hover:underline focus-visible:focus-ring" :class="tone || 'text-ink-blue-8'"
    :aria-label="ariaLabel || `${count.n} ${count.label}`" data-count-door :data-count-n="count.n" :data-count-label="count.label" :data-count-key="countKey">
    <slot :n="count.n">{{ count.n.toLocaleString() }}</slot>
  </RouterLink>
  <RouterLink v-else :to="to" class="rounded-1 tabular-nums hover:underline focus-visible:focus-ring" :class="tone || 'text-ink-blue-8'"><slot /></RouterLink>
</template>
<script setup>
// A number that is a door. With `count` (from the count helper, lifeos/review/counts.py: { n, to: { path, query }, label }) it
// opens the list that shows exactly n rows, so the number and the list cannot disagree; the acceptance script clicks every
// [data-count-door]. With `to` alone (a path or a route, carrying at least one query parameter, all=1 when it means everything,
// so the list shows exactly that and not a remembered view) it is a plain link to the list that produced the text.
defineProps({ count: Object, to: [Object, String], tone: String, ariaLabel: String, countKey: String })
</script>
