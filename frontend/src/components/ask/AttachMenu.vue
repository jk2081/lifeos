<template>
  <!-- +: attach files or a photo to the message; the rest of what + Capture used to add (a goal, a note, an important date, a thing for Someday) -->
  <Dropdown :options="options" placement="top-start">
    <Button :size="size" variant="ghost" icon="lucide-plus" label="Add a file or something new" tooltip="Add" data-ask-attach />
  </Dropdown>
  <FilePick ref="picker" multiple class="hidden" aria-label="Choose files" data-ask-file-input @files="addFiles" />
  <FilePick v-if="camera" ref="shot" accept="image/*" capture="environment" class="hidden" aria-label="Take a photo" data-ask-camera-input @files="addFiles" />
  <Button v-if="camera" class="md:hidden" :size="size" variant="ghost" icon="lucide-camera" label="Take a photo" tooltip="Camera" data-ask-camera @click="shot.open()" />
</template>
<script setup>
import { computed, ref } from 'vue'
import { Button, Dropdown } from 'frappe-ui'
import FilePick from '@/components/ui/FilePick.vue'
import { addFiles, ask } from '@/lib/ask'
import { canWrite, store } from '@/lib/store'

defineProps({ size: { type: String, default: 'md' }, camera: { type: Boolean, default: true } })
const picker = ref(null)
const shot = ref(null)
function make(kind) {
  ask.open = false
  store.newKind = kind
}
const options = computed(() => [
  { label: 'Files or a photo', icon: 'lucide-paperclip', onClick: () => picker.value.open() },
  ...(canWrite() ? [{ label: 'Goal', icon: 'lucide-target', onClick: () => make('goal') }, { label: 'Note', icon: 'lucide-file-text', onClick: () => make('note') },
    { label: 'Important date', icon: 'lucide-cake', onClick: () => make('date') }, { label: 'Park on Someday', icon: 'lucide-lightbulb', onClick: () => make('someday') }] : []),
])
</script>
