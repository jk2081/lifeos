<template>
  <RouterLink :to="to" class="rounded-1 tabular-nums text-ink-blue-8 hover:underline focus-visible:focus-ring"><slot /></RouterLink>
</template>
<script setup>
// A number that is a door: it links to the list that produced it. The link must carry at least one query parameter
// (all=1 when it means everything), so the list shows exactly that and not a remembered view.
defineProps({ to: { type: [Object, String], required: true } })
</script>
