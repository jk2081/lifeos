<template>
  <section v-if="rows.length">
    <SectionHead>Linked records</SectionHead>
    <Card flush>
      <Row v-for="r in rows" :key="r.doctype + r.name" :pane="refOfRoute(r.route)" :label="r.title" @click="!refOfRoute(r.route) && openRoute(r.route)">
        <div class="min-w-0 flex-1">
          <div class="break-words text-base-medium text-ink-gray-9">{{ r.title }}</div>
          <div class="text-sm text-ink-gray-6">{{ r.kind }} · {{ r.why }}</div>
        </div>
      </Row>
    </Card>
  </section>
</template>
<script setup>
// Records that link to this one with [[Title]], plus records tied to it by a field.
import { onMounted, ref, watch } from 'vue'
import Card from './ui/Card.vue'
import Row from './ui/Row.vue'
import SectionHead from './ui/SectionHead.vue'
import { api } from '@/lib/api'
import { openRoute, refOfRoute } from '@/lib/pane'

const props = defineProps({ doctype: String, name: String, reload: { type: Number, default: 0 } })
const rows = ref([])
async function load() {
  if (!props.name) return
  try {
    rows.value = await api('links.backlinks', { doctype: props.doctype, name: props.name })
  } catch (e) {
    rows.value = []
  }
}
onMounted(load)
watch(() => [props.name, props.reload], load)
</script>
