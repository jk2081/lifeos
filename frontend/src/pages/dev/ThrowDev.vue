<template>
  <!-- `kind=patch`: the bug fix 1 failure itself, a teleport mounted before its target exists and then updated -->
  <Teleport v-if="kind === 'patch'" to="#lifeos-no-such-target"><Button :label="`Tick ${n}`" /></Teleport>
  <div class="page-body" data-throw-dev>{{ kind === 'render' ? boom() : `Tick ${n}` }}</div>
</template>
<script setup>
// Development only (bug fix 1): a screen that fails on purpose, so the acceptance run can check the error boundary.
// `?kind=render` throws while drawing; `?kind=patch` fails inside Vue's patching a moment after it mounts.
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button } from 'frappe-ui'

const route = useRoute()
const kind = computed(() => route.query.kind || 'render')
const n = ref(0)
function boom() {
  throw new Error('A screen forced to fail (development check)')
}
onMounted(() => setTimeout(() => (n.value += 1), 300))
</script>
