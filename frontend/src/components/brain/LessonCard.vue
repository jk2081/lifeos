<template>
  <div class="flex flex-col gap-2 border-b border-outline-gray-1 py-3 last:border-b-0" :data-lesson="lesson.name" :data-status="lesson.status">
    <div class="flex flex-wrap items-center gap-2">
      <Badge :theme="STATUS[lesson.status] || 'gray'" :label="lesson.status === 'Proposed' ? 'Lesson' : lesson.status" />
      <RouterLink class="text-base-medium text-ink-blue-8 hover:underline" :to="`/brain/skills/${lesson.skill}`" data-lesson-skill>{{ lesson.skill_title || lesson.skill }}</RouterLink>
      <span v-if="lesson.status === 'Accepted'" class="text-sm text-ink-gray-6" data-lesson-version>made version {{ lesson.skill_version }}</span>
      <span v-else-if="lesson.status === 'Removed'" class="text-sm text-ink-gray-6">removed in version {{ lesson.removed_version }}</span>
      <Badge v-if="lesson.edited" theme="gray" label="Edited" />
    </div>
    <FormControl v-if="editing" v-model="draft" type="textarea" :rows="3" aria-label="The lesson" data-lesson-text />
    <p v-else class="break-words text-base text-ink-gray-9" data-lesson-words>{{ lesson.text }}</p>
    <details class="text-sm text-ink-gray-6" data-lesson-corrections>
      <summary class="cursor-pointer focus-visible:focus-ring">From {{ plural(lesson.corrections.length, 'correction') }}</summary>
      <ul class="mt-1 flex flex-col gap-0.5">
        <li v-for="c in lesson.corrections" :key="c.name">{{ c.detail }} <span class="text-ink-gray-6">“{{ c.capture_title }}”</span></li>
      </ul>
    </details>
    <template v-if="lesson.status === 'Proposed'">
      <details v-if="lesson.before !== undefined" class="text-sm text-ink-gray-6">
        <summary class="cursor-pointer focus-visible:focus-ring">What changes in the skill</summary>
        <DiffView class="mt-1" :before="lesson.before" :after="afterText" data-lesson-diff />
      </details>
      <p v-if="error" class="text-sm text-ink-red-8" role="alert" data-lesson-error>{{ error }}</p>
      <div v-if="canEdit" class="flex flex-wrap items-center gap-2">
        <Button variant="solid" label="Accept" :loading="busy === 'accept'" :disabled="!!busy" data-lesson-accept @click="accept" />
        <Button v-if="!editing" label="Edit" :disabled="!!busy" data-lesson-edit @click="startEdit" />
        <Button v-else label="Cancel" :disabled="!!busy" @click="editing = false" />
        <Button label="Reject" :loading="busy === 'reject'" :disabled="!!busy" data-lesson-reject @click="reject" />
        <span class="text-sm text-ink-gray-6">Accepting tries it on the skill's examples first.</span>
      </div>
    </template>
    <div v-else-if="lesson.status === 'Accepted' && canEdit" class="flex flex-wrap items-center gap-2">
      <Button label="Remove" :loading="busy === 'remove'" :disabled="!!busy" data-lesson-remove @click="remove" />
      <span class="text-sm text-ink-gray-6">Removing makes a new version of the skill without it.</span>
    </div>
  </div>
</template>
<script setup>
// A lesson (issue 30): what the owner's corrections taught a skill, in words. Proposed: Accept (tried on the skill's examples first),
// Edit, Reject, and what it would change as a diff. Accepted: the version it made, and Remove (a new version without it).
import { computed, ref } from 'vue'
import { Badge, Button, FormControl, toast } from 'frappe-ui'
import DiffView from '@/components/DiffView.vue'
import { errorText } from '@/lib/api'
import { brainData } from '@/data/brain'

const props = defineProps({ lesson: { type: Object, required: true }, canEdit: Boolean })
const emit = defineEmits(['changed'])
const STATUS = { Proposed: 'blue', Accepted: 'green', Removed: 'gray', Rejected: 'gray' }
const editing = ref(false)
const draft = ref('')
const busy = ref('')
const error = ref('')
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`
// the diff follows the words being edited
const afterText = computed(() => {
  if (!editing.value || draft.value === props.lesson.text) return props.lesson.after
  return (props.lesson.after || '').replace(props.lesson.text, draft.value.replace(/\s+/g, ' ').trim())
})
function startEdit() { draft.value = props.lesson.text; editing.value = true }
async function act(name, method, args, done) {
  busy.value = name
  error.value = ''
  try {
    await brainData.lessons[method]({ lesson: props.lesson.name, ...args })
    toast.success(done)
    editing.value = false
    emit('changed')
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = ''
  }
}
const accept = () => act('accept', 'accept', editing.value ? { text: draft.value } : {}, 'Added to the skill as a new version.')
const reject = () => act('reject', 'reject', {}, 'Rejected.')
const remove = () => act('remove', 'remove', {}, 'Removed. The skill has a new version without it.')
</script>
