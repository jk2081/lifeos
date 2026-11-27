<template>
  <input ref="el" type="file" :multiple="multiple" :accept="accept || undefined" :capture="capture || undefined" @change="changed" />
</template>
<script setup>
// The file chooser of the browser, for the places that only want the chosen File objects (frappe-ui's FileUploader uploads by itself). It is the one
// raw <input type="file"> of the app; give it `class="hidden"` and open it from a Button with the exposed open(), or put it inside a <label>.
import { ref } from 'vue'

defineProps({ multiple: Boolean, accept: { type: String, default: '' }, capture: { type: String, default: '' } })
const emit = defineEmits(['files'])
const el = ref(null)
function changed(e) {
  emit('files', [...e.target.files])
  e.target.value = ''
}
defineExpose({ open: () => el.value.click() })
</script>
