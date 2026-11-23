<template>
  <Dialog v-model:open="open" :title="title" size="md" data-sort-open-dialog
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: button, variant: 'solid', theme: mode === 'drop' ? 'red' : undefined, loading: busy, onClick: submit }]">
    <div class="flex flex-col gap-3">
      <template v-if="mode === 'focus'">
        <p class="text-base text-ink-gray-8">“{{ goal?.title }}” becomes a focus: ongoing work with a standard and principles. Its tasks move to a new annual goal under it. Name that goal, say when it is done and by when.</p>
        <FormControl v-model="v.title" label="Annual goal" placeholder="For example: All three estates on ERPNext stores" data-sort-title />
        <FormControl v-model="v.done_when" label="Done when" placeholder="What is true when it is done" data-sort-done-when />
        <DatePicker v-model="v.target_date" format="D MMM YYYY" label="Target date" data-sort-date />
      </template>
      <template v-else-if="mode === 'annual'">
        <p class="text-base text-ink-gray-8">“{{ goal?.title }}” becomes an annual goal. Choose the date it should be done by.</p>
        <DatePicker v-model="v.target_date" format="D MMM YYYY" label="Target date" data-sort-date />
      </template>
      <p v-else class="text-base text-ink-gray-8">Drop “{{ goal?.title }}”? Its tasks and notes go to the Archive with it. Nothing is deleted.</p>
      <ErrorMessage v-if="error" :message="error" data-sort-error />
    </div>
  </Dialog>
</template>
<script setup>
// What becomes of an Open goal (issue 57): a focus (with an annual goal that holds its tasks), an annual goal, or dropped.
import { computed, reactive, ref, watch } from 'vue'
import { DatePicker, Dialog, ErrorMessage, FormControl, toast } from 'frappe-ui'
import { errorText } from '@/lib/api'
import { goalsData } from '@/data/goals'

const props = defineProps({ modelValue: Boolean, goal: { type: Object, default: null }, mode: { type: String, default: 'annual' } })
const emit = defineEmits(['update:modelValue', 'done'])
const open = ref(false)
const busy = ref(false)
const error = ref('')
const v = reactive({ title: '', done_when: '', target_date: '' })
const title = computed(() => ({ focus: 'Make it a focus', annual: 'Make it an annual goal', drop: 'Drop this goal' })[props.mode])
const button = computed(() => ({ focus: 'Make a focus', annual: 'Make it annual', drop: 'Drop it' })[props.mode])
watch(() => props.modelValue, (o) => {
  open.value = o
  if (o) Object.assign(v, { title: props.goal?.title || '', done_when: props.goal?.done_when_line || '', target_date: '' }), (error.value = '')
})
watch(open, (o) => emit('update:modelValue', o))
async function submit() {
  busy.value = true
  error.value = ''
  try {
    const args = { goal: props.goal.name, action: props.mode, ...(props.mode !== 'drop' && v.target_date ? { target_date: v.target_date } : {}) }
    if (props.mode === 'focus') Object.assign(args, { title: v.title, done_when: v.done_when })
    const res = await goalsData.focus.sort_open(args)
    toast.success({ focus: 'Focus made', annual: 'Now an annual goal', drop: 'Dropped' }[props.mode])
    open.value = false
    emit('done', res)
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}
</script>
