<template>
  <div class="flex flex-col gap-4" data-connections>
    <p class="text-sm text-ink-gray-6">Each outside system an agent brings things in from: where its items are filed and what the agent does with them.
      No passwords or keys are kept here; the agents hold their own access.</p>
    <Card flush>
      <div v-for="c in rows" :key="c.name" class="flex flex-col gap-2 border-b border-outline-gray-1 py-3 last:border-b-0" :data-connection="c.system">
        <div class="flex flex-wrap items-center gap-2">
          <div class="min-w-0 flex-1"><div class="text-base-medium text-ink-gray-9">{{ c.label }} <span class="text-sm font-normal text-ink-gray-6">{{ c.system }}</span></div>
            <div class="text-sm" :class="c.quiet ? 'text-ink-amber-9' : 'text-ink-gray-6'" data-last-received>
              <span v-if="c.quiet" class="lucide-triangle-alert mr-1 inline-block size-3.5 align-[-2px]" aria-hidden="true" />{{ lastReceived(c) }}</div></div>
          <Switch :model-value="!!c.active" :disabled="!writable" label="Active" @update:model-value="(v) => save(c, { active: v ? 1 : 0 })" />
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Pick :model-value="c.default_area" :options="areaOptions()" prefix="Area: " placeholder="default area" :disabled="!writable" @update:model-value="(v) => save(c, { default_area: v || '' })" />
          <Pick :model-value="c.default_project" :options="projectOptions(c)" prefix="Project: " placeholder="default project" :disabled="!writable" @update:model-value="(v) => save(c, { default_project: v || '' })" />
          <Select class="w-36" :model-value="c.default_intent" :options="INTENTS" :disabled="!writable" aria-label="Default intent" @update:model-value="(v) => save(c, { default_intent: v })" />
        </div>
      </div>
      <Empty v-if="loaded && !rows.length" title="No connections yet." hint="A connection appears when an agent first brings something in with a source_system, or when you import a chat export below." />
    </Card>

    <section data-chat-import>
      <SectionHead>Import chat history</SectionHead>
      <Card class="flex flex-col gap-3">
        <p class="text-sm text-ink-gray-6">Upload a data export from Claude or ChatGPT (a .zip, up to 1 GB). Each chat becomes an AI chat in Sources, with its transcript;
          a chat imported before is updated, not repeated. Summaries are left for the agent. Area and project come from the connection above.</p>
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
// Settings, This space, Connections (UX fixes, set 4): one row per outside system with its filing defaults and when something
// last arrived (a warning when it has been quiet too long), and the import of Claude and ChatGPT data exports.
import { onBeforeUnmount, ref, watch } from 'vue'
import { Button, FileUploader, Progress, Select, Switch, toast } from 'frappe-ui'
import Card from '../ui/Card.vue'
import SectionHead from '../ui/SectionHead.vue'
import Empty from '../Empty.vue'
import Pick from '../Pick.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { areaOptions, loadLookups, lookups } from '@/lib/lookups'
import { dateTime } from '@/lib/dates'

const props = defineProps({ space: String, writable: Boolean })
const INTENTS = [{ label: 'Process', value: 'Process' }, { label: 'Add to wiki', value: 'Add to wiki' }, { label: 'Just keep', value: 'Just keep' }]
const KINDS = [{ system: 'claude', label: 'Claude' }, { system: 'chatgpt', label: 'ChatGPT' }]
const rows = ref([])
const loaded = ref(false)
const status = ref({})
let timer = null

const projectOptions = (c) => lookups.projects.filter((p) => !c.default_area || p.area === c.default_area).map((p) => ({ value: p.name, label: p.title }))
function lastReceived(c) {
  if (!c.last_received_on) return c.quiet ? 'Nothing has arrived yet' : 'Nothing yet'
  const what = c.last_received_what ? `${c.last_received_what}, ` : ''
  return `Last received: ${what}${dateTime(c.last_received_on)}${c.quiet ? ` · nothing for more than ${Math.round(c.quiet_hours / 24)} days` : ''}`
}
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
  loadLookups()
  const res = await tryCall(() => api('connections.list', { space: props.space }))
  if (res) rows.value = res.connections
  loaded.value = true
  for (const k of KINDS) status.value[k.system] = await tryCall(() => api('connections.import_status', { space: props.space, system: k.system }))
  poll()
}
async function save(c, values) {
  const res = await tryCall(() => api('connections.save', { name: c.name, ...values }), 'Saved.')
  if (res) Object.assign(c, res)
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
