<template>
  <div class="panel-back" @click="$emit('close')"></div>
  <aside class="panel" role="dialog" :aria-label="title">
    <div class="panel-hd">
      <div style="min-width: 0">
        <div class="h1" style="font-size: 16px">{{ title }}</div>
        <div v-if="sub" class="sub">{{ sub }}</div>
      </div>
      <div style="display: flex; gap: 8px; align-items: center">
        <slot name="actions" />
        <button class="bt s ic" type="button" aria-label="Close" @click="$emit('close')"><Ico d="M6 6l12 12M18 6L6 18" /></button>
      </div>
    </div>
    <div class="panel-bd"><slot /></div>
  </aside>
</template>
<script setup>
import { onMounted, onUnmounted } from 'vue'
import Ico from './Ico.vue'

defineProps({ title: String, sub: String })
const emit = defineEmits(['close'])
const onEsc = () => emit('close')
onMounted(() => window.addEventListener('lifeos-escape', onEsc))
onUnmounted(() => window.removeEventListener('lifeos-escape', onEsc))
</script>
