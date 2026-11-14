<template>
  <div class="empty"><b>{{ title }}</b><slot>{{ hint }}</slot></div>
</template>
<script setup>
defineProps({ title: String, hint: String })
</script>
