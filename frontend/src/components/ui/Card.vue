<template>
  <component :is="as" class="rounded-5 border border-outline-gray-2 bg-surface-base" :class="[flush ? 'px-4' : 'p-4', tint && 'bg-surface-gray-1']"><slot /></component>
</template>
<script setup>
// A bordered surface. `flush` leaves the vertical padding to the rows inside it.
defineProps({ as: { type: String, default: 'div' }, flush: Boolean, tint: Boolean })
</script>
