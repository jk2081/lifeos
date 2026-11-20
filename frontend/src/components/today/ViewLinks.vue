<template>
  <nav v-if="links.length" class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-gray-6" aria-label="Other views" data-view-links>
    <span>Also:</span>
    <RouterLink v-for="l in links" :key="l.label" class="text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="l.to">{{ l.label }}</RouterLink>
  </nav>
</template>
<script setup>
// The views of a rhythm that are not its calendar (the weekly review, habits, the 12 Week grid): a quiet line of links under the header.
import { RouterLink } from 'vue-router'
defineProps({ links: { type: Array, default: () => [] } })
</script>
