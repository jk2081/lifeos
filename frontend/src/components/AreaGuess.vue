<template>
  <Button v-if="task.area_guessed" size="sm" class="relative !h-5 shrink-0 !rounded !bg-surface-violet-2 !px-1.5 !text-ink-violet-7 hover:!bg-surface-violet-3"
    :disabled="readonly || busy" :aria-label="`Confirm ${task.area_name}, the area the Brain guessed (${percent}% sure)`"
    :title="readonly ? 'The Brain guessed this area' : 'The Brain guessed this area. Tap to confirm it, or change it in the task.'"
    data-area-guess @click.stop="confirmArea">
    ✦ {{ full ? `Guessed ${task.area_name}, ${percent}% sure · Confirm` : `${task.area_name} · ${percent}%` }}
  </Button>
</template>
<script setup>
// Issue 13: an area the Brain guessed for a task, with how sure it was. One tap confirms it and the mark goes.
import { todayData } from '@/data/today'
import { computed, ref } from 'vue'
import { Button, toast } from 'frappe-ui'
import { errorText } from '@/lib/api'

const props = defineProps({ task: Object, readonly: Boolean, full: Boolean })
const emit = defineEmits(['confirmed'])
const busy = ref(false)
const percent = computed(() => Math.round(props.task.area_confidence || 0))

async function confirmArea() {
  busy.value = true
  try {
    const res = await todayData.tasks.confirm_area({ task: props.task.name })
    // the row is the list's own object: clearing the mark here updates it in place
    Object.assign(props.task, { area_guessed: 0, area_confidence: 0 })
    emit('confirmed', res)
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.value = false
  }
}
</script>
