<template>
  <div :class="bare ? 'bare' : 'cd'" class="hbs" :style="`grid-template-columns: repeat(${Math.min(Math.max(habits.length, 4), 6)}, minmax(0, 1fr))`">
    <div v-for="h in habits" :key="h.habit">
      <button class="hb" :class="{ on: h.done }" type="button" :aria-label="`${h.title}, ${h.done ? 'done' : 'not done'}`" :aria-pressed="h.done"
        @click="$emit('toggle', h)">{{ h.title.slice(0, 1).toUpperCase() }}</button>
      <div class="mt nm">{{ h.title }}</div>
    </div>
  </div>
</template>
<script setup>
defineProps({ habits: Array, bare: Boolean })
defineEmits(['toggle'])
</script>
<style scoped>
.hbs { display: grid; gap: 8px; text-align: center; }
.nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
