<template>
  <ChangeView :name="name" @loaded="(c) => $emit('meta', { title: c.note_title, sub: `${c.change_type} · ${c.by}`, fullPage: `/library/${c.note}` })" @undone="$emit('changed')" />
</template>
<script setup>
// A wiki change in the pane, from the Wiki's Changes tab and a page's History.
import ChangeView from '../ChangeView.vue'
defineProps({ name: String, type: String, tab: String })
defineEmits(['meta', 'missing', 'changed', 'close'])
</script>
