<template>
  <div class="flex flex-col gap-4" data-chat-import-section>
    <section data-chat-import>
      <SectionHead>Import chat history</SectionHead>
      <Card class="flex flex-col gap-3">
        <p class="text-sm text-ink-gray-6">Upload a data export from Claude or ChatGPT (a .zip, up to 1 GB). Each chat becomes an AI chat in Library, Captures, with its transcript;
          a chat imported before is updated, not repeated. Summaries are left for the agent. Area and goal come from the source in Brain, Sources.</p>
        <div v-for="k in KINDS" :key="k.system" class="flex flex-wrap items-center gap-2" :data-import="k.system">
          <FileUploader v-if="writable" file-types=".zip,application/zip" :private="true" @success="(f) => start(k.system, f)" @failure="(e) => toast.error(errorText(e))">
            <template #default="{ openFileSelector, uploading, progress: p }">
              <Button :label="uploading ? `Uploading ${p}%` : `Import a ${k.label} export`" icon-left="lucide-upload" :loading="uploading" :disabled="busy(k.system)" @click="openFileSelector" />
            </template>
          </FileUploader>
          <span class="text-sm" :class="status[k.system]?.status === 'Failed' ? 'text-ink-red-8' : 'text-ink-gray-7'" data-import-status>{{ describe(status[k.system]) }}</span>
          <Progress v-if="busy(k.system) && status[k.system]?.total" class="w-40" :value="Math.round((100 * (status[k.system].done || 0)) / status[k.system].total)" />
        </div>
        <p class="text-sm text-ink-gray-6">You can leave this page while an import runs.</p>
      </Card>
    </section>
  </div>
</template>
<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { Button, FileUploader, Progress, toast } from 'frappe-ui'
import Card from '../ui/Card.vue'
import SectionHead from '../ui/SectionHead.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { dateTime } from '@/lib/dates'

// Settings > Advanced > Import and export: the chat import (the connections are Brain > Sources, issue 19)
const props = defineProps({ space: String, writable: Boolean })
const KINDS = [{ system: 'claude', label: 'Claude' }, { system: 'chatgpt', label: 'ChatGPT' }]
const status = ref({})
let timer = null

const busy = (system) => ['Queued', 'Reading', 'Importing'].includes(status.value[system]?.status)
function describe(s) {
  if (!s || !s.status) return ''
  if (s.status === 'Failed') return `Failed: ${s.error || 'unknown error'}`
  const counts = [`${s.created || 0} new`, `${s.updated || 0} updated`, `${s.unchanged || 0} unchanged`, s.skipped ? `${s.skipped} could not be read` : ''].filter(Boolean).join(', ')
  if (s.status === 'Done') return `Done ${dateTime(s.finished_on)}: ${counts}`
  if (s.status === 'Importing') return `Importing ${s.done || 0} of ${s.total || 0}: ${counts}`
  return s.status === 'Queued' ? 'Waiting to start…' : 'Reading the export…'
}
async function load() {
  for (const k of KINDS) status.value[k.system] = await tryCall(() => api('connections.import_status', { space: props.space, system: k.system }))
  poll()
}
async function start(system, file) {
  const res = await tryCall(() => api('connections.start_import', { space: props.space, system, file_url: file.file_url }), 'Import started.')
  if (res) { status.value[system] = res; poll() }
}
function poll() {
  clearTimeout(timer)
  if (!KINDS.some((k) => busy(k.system))) return
  timer = setTimeout(async () => {
    for (const k of KINDS) if (busy(k.system)) status.value[k.system] = await tryCall(() => api('connections.import_status', { space: props.space, system: k.system }))
    if (!KINDS.some((k) => busy(k.system))) load()
    else poll()
  }, 2000)
}
watch(() => props.space, load, { immediate: true })
onBeforeUnmount(() => clearTimeout(timer))
</script>
