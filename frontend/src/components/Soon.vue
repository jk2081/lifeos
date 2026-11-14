<template>
  <header class="hd"><div><h1 class="h1">{{ title }}</h1><div class="sub">This screen is not built yet.</div></div></header>
  <div class="bd"><div class="cd empty"><b>{{ title }} is coming.</b>It arrives in a later milestone of this build.</div></div>
</template>
<script setup>
defineProps({ title: String })
</script>
