<template>
  <header class="hd" :class="{ tabs }">
    <div style="min-width: 0">
      <div v-if="crumb" class="crumb"><RouterLink :to="crumb.to">{{ crumb.label }}</RouterLink> / {{ crumb.here }}</div>
      <h1 class="h1">{{ title }}<span v-if="count !== null && count !== undefined" class="cnt" data-lv-count :aria-label="`${count} matching`">{{ count }}</span></h1>
      <div v-if="sub || $slots.sub" class="sub"><slot name="sub">{{ sub }}</slot></div>
    </div>
    <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center"><slot /></div>
  </header>
</template>
<script setup>
defineProps({ title: String, sub: String, crumb: Object, tabs: Boolean, count: { type: Number, default: null } })
</script>
