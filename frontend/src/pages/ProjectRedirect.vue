<template>
  <div class="page-body"><Card><Empty :title="missing ? 'This project was not found.' : 'Opening the goal this project became…'"
    :hint="missing ? 'It may belong to another space.' : 'Projects became open-ended goals.'" /></Card></div>
</template>
<script setup>
// /projects/:id from before set 6: the page of the goal the project became, with the query carried over.
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import { api } from '@/lib/api'

const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()
const missing = ref(false)
onMounted(async () => {
  try {
    const r = await api('goals.for_project', { project: props.id })
    router.replace({ path: `/goals/${r.goal}`, query: route.query })
  } catch (e) {
    missing.value = true
  }
})
</script>
