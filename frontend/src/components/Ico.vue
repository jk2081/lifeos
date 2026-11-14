<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="stroke"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="d" /></svg>
</template>
<script setup>
defineProps({ d: String, size: { type: [Number, String], default: 16 }, stroke: { type: [Number, String], default: 1.8 } })
</script>
