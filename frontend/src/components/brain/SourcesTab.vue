<template>
  <PageHead title="Brain" sub="Where information comes from. The Brain reads only what you switch on." />
  <div class="page-body flex max-w-6xl flex-col gap-6" data-brain-sources :data-loaded="loaded ? 1 : 0">
    <section class="flex flex-col gap-3" data-connected>
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-base-medium text-ink-gray-9">Connected · <span data-connected-count>{{ connected.length }}</span></h2>
        <Button v-if="writable" variant="solid" icon-left="lucide-plus" label="Add a source" data-add-source @click="toAddMore" />
      </div>
      <div v-if="connected.length" class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Card v-for="c in connected" :key="c.name" class="relative flex flex-col gap-2 hover:bg-surface-gray-1" data-source-card :data-system="c.system" :data-active="c.active" :data-week="c.this_week">
          <button type="button" class="absolute inset-0 rounded-5 focus-visible:focus-ring" :aria-label="`Open ${c.label}`" data-source-open @click="openSettings(c)" />
          <div class="flex items-center gap-3">
            <span class="flex size-9 flex-none items-center justify-center rounded-4 bg-surface-gray-2 text-sm-medium text-ink-gray-8" aria-hidden="true">{{ c.icon }}</span>
            <div class="min-w-0 flex-1"><div class="truncate text-base-medium text-ink-gray-9">{{ c.label }}</div><div class="truncate text-sm text-ink-gray-6">{{ c.kind }}</div></div>
            <Switch class="relative" :model-value="!!c.active" :disabled="!writable" :label="c.active ? 'On' : 'Off'" data-source-switch @update:model-value="(v) => toggle(c, v)" />
          </div>
          <p class="text-sm text-ink-gray-6" data-source-line>{{ c.line }}</p>
          <p v-if="c.active && c.quiet" class="text-sm text-ink-amber-9" data-source-quiet>Nothing has arrived for a while.</p>
        </Card>
      </div>
      <Card v-else-if="loaded" class="py-2" data-sources-empty>
        <Empty title="Nothing is connected yet.">
          <p class="mt-1">Things you add yourself are always read. Email, a calendar or an agent show up here once you switch them on below.</p>
          <Button v-if="writable" class="mt-3" variant="solid" icon-left="lucide-plus" label="Add a source" data-add-source-empty @click="toAddMore" />
        </Empty>
      </Card>
    </section>

    <section ref="more" class="flex flex-col gap-3" data-add-more>
      <h2 class="text-base-medium text-ink-gray-9">Add more <span class="text-sm font-normal text-ink-gray-6">One click each. Nothing is read until you switch it on.</span></h2>
      <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <div v-for="t in available" :key="t.system" class="relative flex flex-col items-center gap-0.5 rounded-5 border border-dashed border-outline-gray-2 px-3 py-4 text-center"
          :class="t.always_on ? '' : 'hover:bg-surface-gray-1'" data-source-tile :data-system="t.system" :data-always-on="t.always_on ? 1 : 0">
          <button v-if="writable && !t.always_on" type="button" class="absolute inset-0 rounded-5 focus-visible:focus-ring" :aria-label="`Add ${t.label}`" data-tile-add @click="add(t)" />
          <span class="text-base-medium text-ink-gray-9">{{ t.label }}</span>
          <span class="text-sm text-ink-gray-6">{{ t.hint }}</span>
          <Badge v-if="t.always_on" class="mt-1" theme="green" label="Always on" />
        </div>
        <div class="relative flex flex-col items-center gap-0.5 rounded-5 border border-dashed border-outline-gray-2 px-3 py-4 text-center hover:bg-surface-gray-1" data-source-tile data-system="other-agent">
          <button v-if="writable" type="button" class="absolute inset-0 rounded-5 focus-visible:focus-ring" aria-label="Add another agent" data-tile-other @click="otherOpen = true" />
          <span class="text-base-medium text-ink-gray-9">Another agent</span><span class="text-sm text-ink-gray-6">Any MCP agent</span>
        </div>
        <div v-for="t in coming" :key="t.system" class="flex flex-col items-center gap-0.5 rounded-5 border border-dashed border-outline-gray-2 px-3 py-4 text-center opacity-80"
          data-source-tile data-tile-coming :data-system="t.system" aria-disabled="true">
          <span class="text-base-medium text-ink-gray-9">{{ t.label }}</span><span class="text-sm text-ink-gray-6">{{ t.hint }}</span>
          <Badge class="mt-1" theme="gray" label="Coming" />
        </div>
      </div>
    </section>
  </div>

  <Dialog v-model:open="settingsOpen" :title="current?.label || 'Source'" :actions="writable ? [{ label: 'Save', variant: 'solid', onClick: save }] : []">
    <template #default>
      <div v-if="current" class="flex flex-col gap-3" data-source-settings :data-system="current.system">
        <p class="text-sm text-ink-gray-6">{{ current.kind }} · {{ current.line }}</p>
        <p class="text-sm" :class="current.quiet ? 'text-ink-amber-9' : 'text-ink-gray-6'">{{ lastReceived(current) }}</p>
        <Switch v-model="draft.active" :disabled="!writable" :label="draft.active ? 'On: Life OS accepts captures from it' : 'Off: Life OS refuses captures from it'" data-settings-active />
        <div data-settings-intent><FormControl v-model="draft.default_intent" type="select" label="Default intent" :options="INTENTS" :disabled="!writable" /></div>
        <div class="flex flex-wrap items-center gap-2"><span class="w-24 text-sm text-ink-gray-6">Default area</span>
          <span data-settings-area><Pick v-model="draft.default_area" :options="areaOptions()" placeholder="No default area" :disabled="!writable" @update:model-value="draft.default_goal = null" /></span></div>
        <div class="flex flex-wrap items-center gap-2"><span class="w-24 text-sm text-ink-gray-6">Default goal</span>
          <span data-settings-goal><Pick v-model="draft.default_goal" :options="goalOptions" placeholder="No default goal" :disabled="!writable" /></span></div>
        <p class="text-sm text-ink-gray-6">What this source sends without an area, goal or intent of its own is filed with these. No passwords or keys are kept here.</p>
      </div>
    </template>
  </Dialog>

  <Dialog v-model:open="otherOpen" title="Add another agent" :actions="[{ label: 'Add', variant: 'solid', onClick: addOther }]">
    <template #default>
      <div class="flex flex-col gap-2" data-other-agent>
        <FormControl v-model="otherName" label="Name" placeholder="For example Atlas" @keydown.enter="addOther" />
        <p class="text-sm text-ink-gray-6">The agent sends this as its source_system. It can bring things in once it has its own user and key (Settings, People and agents).</p>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
// Brain > Sources (issue 19): where information comes from, switched on one by one. A card for each connected source
// (a Life Connection), tiles for what can be added, and "Coming" tiles for what is not built yet. A source that is off
// makes the server refuse its captures; nothing it brought in is deleted.
import { computed, ref, watch } from 'vue'
import { Badge, Button, Dialog, FormControl, Switch } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import Pick from '@/components/Pick.vue'
import PageHead from '@/components/PageHead.vue'
import { api, tryCall } from '@/lib/api'
import { areaOptions, loadLookups, lookups } from '@/lib/lookups'
import { dateTime } from '@/lib/dates'
import { canWrite, store } from '@/lib/store'

const INTENTS = [{ label: 'Process', value: 'Process' }, { label: 'Add to wiki', value: 'Add to wiki' }, { label: 'Just keep', value: 'Just keep' }]
const writable = computed(() => canWrite() && !store.isAgent)
const connected = ref([])
const available = ref([])
const coming = ref([])
const loaded = ref(false)
const more = ref(null)
const settingsOpen = ref(false)
const current = ref(null)
const draft = ref({})
const otherOpen = ref(false)
const otherName = ref('')

const goalOptions = computed(() => (lookups.goals || []).filter((g) => !draft.value.default_area || g.area === draft.value.default_area).map((g) => ({ value: g.name, label: g.title })))
const toAddMore = () => more.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
function lastReceived(c) {
  if (!c.last_received_on) return 'Nothing has arrived yet.'
  return `Last received: ${c.last_received_what ? c.last_received_what + ', ' : ''}${dateTime(c.last_received_on)}`
}
async function load() {
  loadLookups()
  const res = await tryCall(() => api('connections.sources', { space: store.space }))
  if (res) { connected.value = res.connected; available.value = res.available; coming.value = res.coming }
  loaded.value = true
}
async function toggle(c, on) {
  const res = await tryCall(() => api('connections.save', { name: c.name, active: on ? 1 : 0 }), on ? `${c.label} is on.` : `${c.label} is off. Nothing it brought in was deleted.`)
  if (res) Object.assign(c, { active: res.active, quiet: res.quiet })
}
function openSettings(c) {
  current.value = c
  draft.value = { active: !!c.active, default_intent: c.default_intent || 'Process', default_area: c.default_area || null, default_goal: c.default_goal || null }
  settingsOpen.value = true
}
async function save() {
  const d = draft.value
  const res = await tryCall(() => api('connections.save', { name: current.value.name, active: d.active ? 1 : 0, default_intent: d.default_intent, default_area: d.default_area || '', default_goal: d.default_goal || '' }), 'Saved.')
  if (!res) return
  settingsOpen.value = false
  await load()
}
async function add(t) {
  const res = await tryCall(() => api('connections.save', { space: store.space, system: t.system, active: 1 }), `${t.label} is on.`)
  if (!res) return
  await load()
  const c = connected.value.find((x) => x.system === t.system)
  if (c) openSettings(c)
}
async function addOther() {
  const system = otherName.value.trim().toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40)
  if (!system) return
  const res = await tryCall(() => api('connections.save', { space: store.space, system, label: otherName.value.trim(), active: 1 }), `${otherName.value.trim()} is on.`)
  if (!res) return
  otherOpen.value = false
  otherName.value = ''
  await load()
  const c = connected.value.find((x) => x.system === system)
  if (c) openSettings(c)
}
watch(() => store.space, load, { immediate: true })
</script>
