<template>
  <Card><Empty title="Opening the goal this project became…" hint="Projects became open-ended goals." /></Card>
</template>
<script setup>
// A link to a project from before set 6 (open=project:NAME): projects became open-ended goals, so the pane asks which goal
// the project became and opens that instead, in place.
import { onMounted } from 'vue'
import Card from '../ui/Card.vue'
import Empty from '../Empty.vue'
import { api } from '@/lib/api'
import { openRef } from '@/lib/pane'

const props = defineProps({ name: String, type: String, tab: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
onMounted(async () => {
  emit('meta', { title: 'Goal' })
  try {
    const r = await api('goals.for_project', { project: props.name })
    openRef('goal:' + r.goal)
  } catch (e) {
    emit('missing')
  }
})
</script>
