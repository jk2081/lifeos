<template>
  <div class="flex flex-col items-start gap-2 px-1 py-4 text-base text-ink-gray-6" data-empty>
    <p class="min-w-0"><slot>{{ line }}</slot></p>
    <slot name="action"><Button v-if="action" size="sm" variant="subtle" :label="action.label" :icon-left="action.icon" data-empty-action @click="run" /></slot>
  </div>
</template>
<script setup>
// What a list says when it has nothing in it: one line on what will appear there and at most one action that fills it. `action` is
// `{ label, icon, to }` (a route) or `{ label, icon, click }` (a function). The `action` slot takes the one control when it is not a button (a field to add the first task). A card with nothing to count shows its number, 0, not this.
import { Button } from 'frappe-ui'
import { useRouter } from 'vue-router'
const props = defineProps({ line: String, action: { type: Object, default: null } })
const emit = defineEmits(['action'])
const router = useRouter()
function run() {
  emit('action')
  if (props.action.click) props.action.click()
  else if (props.action.to) router.push(props.action.to)
}
</script>
