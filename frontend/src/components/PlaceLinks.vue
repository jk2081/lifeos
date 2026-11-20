<template>
  <!-- the pages that live in a place without being one of its tabs (issue 14), as one quiet row at the foot of the place -->
  <nav class="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-outline-gray-1 px-4 py-3 text-sm md:px-7" :aria-label="label" data-place-links>
    <RouterLink v-for="l in links" :key="l.key" class="inline-flex min-h-8 items-center gap-1.5 text-ink-gray-7 hover:text-ink-gray-9 hover:underline focus-visible:focus-ring"
      :to="l.to" :data-place-link="l.key"><span :class="l.icon" class="size-4" aria-hidden="true" />{{ l.label }}</RouterLink>
  </nav>
</template>
<script setup>
// links: [{ key, label, icon, to }]
defineProps({ links: { type: Array, required: true }, label: { type: String, required: true } })
</script>
