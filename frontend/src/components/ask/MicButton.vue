<template>
  <!-- the mic: the recording is turned into text on the server (faster-whisper) and the text goes into the box to check and send; no audio goes to a model -->
  <Button v-if="canRecord" :variant="ask.recording ? 'solid' : 'ghost'" :theme="ask.recording ? 'red' : 'gray'" :size="size" :loading="busy" :icon="ask.recording ? 'lucide-square' : 'lucide-mic'"
    :label="ask.recording ? 'Stop and write it down' : 'Speak your message'" :tooltip="ask.recording ? 'Stop' : 'Speak'" data-ask-mic @click="ask.recording ? stop() : start()" />
</template>
<script setup>
import { computed, onUnmounted, ref } from 'vue'
import { Button, toast } from 'frappe-ui'
import { errorText } from '@/lib/api'
import { ask, transcribe } from '@/lib/ask'

defineProps({ size: { type: String, default: 'md' } })
const emit = defineEmits(['text'])
const busy = ref(false)
const canRecord = computed(() => !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder))
let recorder = null
let stream = null
async function start() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    toast.error('Life OS could not use the microphone. Allow it in your browser settings and try again.')
    return
  }
  const chunks = []
  recorder = new MediaRecorder(stream)
  recorder.ondataavailable = (e) => e.data?.size && chunks.push(e.data)
  recorder.onstop = async () => {
    const type = recorder.mimeType || 'audio/webm'
    const ext = type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm'
    release()
    if (!chunks.length) return
    busy.value = true
    try {
      const text = await transcribe(new Blob(chunks, { type }), `voice-${Date.now()}.${ext}`)
      if (text) emit('text', text)
    } catch (e) { toast.error(errorText(e)) } finally { busy.value = false }
  }
  recorder.start()
  ask.recording = true
}
function stop() {
  if (recorder && recorder.state !== 'inactive') recorder.stop()
  ask.recording = false
}
function release() {
  stream?.getTracks().forEach((t) => t.stop())
  stream = null
  ask.recording = false
}
onUnmounted(release)
</script>
