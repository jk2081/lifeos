<template>
  <div class="px-1 py-4 text-base text-ink-gray-6" data-empty>
    <b class="mb-0.5 block font-medium text-ink-gray-8">{{ title }}</b>
    <slot>{{ hint }}</slot>
  </div>
</template>
<script setup>
// What a list or section says when it has nothing to show: what belongs here and how to add the first one.
defineProps({ title: String, hint: String })
</script>
