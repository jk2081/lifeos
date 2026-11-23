<template>
  <RouterLink :to="count.to" class="rounded-1 tabular-nums hover:underline focus-visible:focus-ring" :class="tone || 'text-ink-blue-8'"
    :aria-label="ariaLabel || `${count.n} ${count.label}`" data-count-door :data-count-n="count.n" :data-count-label="count.label" :data-count-key="countKey">
    <slot :n="count.n">{{ count.n.toLocaleString() }}</slot>
  </RouterLink>
</template>
<script setup>
// A number from the count helper (lifeos/review/counts.py): { n, to: { path, query }, label }. It opens the list that shows
// exactly n rows, so the number and the list cannot disagree. The acceptance script clicks every [data-count-door].
defineProps({ count: { type: Object, required: true }, tone: String, ariaLabel: String, countKey: String })
</script>
