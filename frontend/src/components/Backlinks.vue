<template>
  <section v-if="groups.length">
    <h2 class="sh">Linked records</h2>
    <div class="cd list">
      <div v-for="r in rows" :key="r.doctype + r.name" class="rw rowlink" @click="openRoute(r.route)">
        <div class="grow">
          <div class="ttl">{{ r.title }}</div>
          <div class="mt">{{ r.kind }} · {{ r.why }}</div>
        </div>
      </div>
    </div>
  </section>
</template>
<script setup>
// Records that link to this one with [[Title]], plus records tied to it by a field.
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'
import { openRoute } from '@/lib/pane'

const props = defineProps({ doctype: String, name: String, reload: { type: Number, default: 0 } })
const rows = ref([])
const groups = computed(() => rows.value)
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
