<template>
  <header class="hd" :class="{ tabs }">
    <div style="min-width: 0">
      <div v-if="crumb" class="crumb"><RouterLink :to="crumb.to">{{ crumb.label }}</RouterLink> / {{ crumb.here }}</div>
      <h1 class="h1">{{ title }}</h1>
      <div v-if="sub || $slots.sub" class="sub"><slot name="sub">{{ sub }}</slot></div>
    </div>
    <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center"><slot /></div>
  </header>
</template>
<script setup>
defineProps({ title: String, sub: String, crumb: Object, tabs: Boolean })
</script>
