<template>
  <section v-if="list.length || tab">
    <SectionHead v-if="!tab">Linked records</SectionHead>
    <Card flush>
      <Row v-for="r in list" :key="r.doctype + r.name" :pane="refOfRoute(r.route)" :label="r.title" @click="!refOfRoute(r.route) && openRoute(r.route)">
        <div class="min-w-0 flex-1">
          <div class="break-words text-base-medium text-ink-gray-9">{{ r.title }}</div>
          <div class="text-sm text-ink-gray-6">{{ r.kind }} · {{ r.why }}</div>
        </div>
      </Row>
      <Empty v-if="tab && !list.length" title="Nothing links here yet." hint="Records that link to this one with [[Title]], or are filed under it, show here." />
    </Card>
  </section>
</template>
<script setup>
// Records that link to this one with [[Title]], plus records tied to it by a field.
// On a page it loads its own rows and hides when there are none. In a pane's Links tab (`tab`) it is given the rows,
// loaded with the pane so the tab can show their count, and says so when there are none.
import { computed, onMounted, ref, watch } from 'vue'
import Card from './ui/Card.vue'
import Row from './ui/Row.vue'
import SectionHead from './ui/SectionHead.vue'
import Empty from './Empty.vue'
import { loadBacklinks } from '@/lib/links'
import { openRoute, refOfRoute } from '@/lib/pane'

const props = defineProps({ doctype: String, name: String, reload: { type: Number, default: 0 }, items: { type: Array, default: null }, tab: Boolean })
const rows = ref([])
const list = computed(() => props.items || rows.value)
async function load() {
  if (!props.name || props.items) return
  rows.value = await loadBacklinks(props.doctype, props.name)
}
onMounted(load)
watch(() => [props.name, props.reload], load)
</script>
