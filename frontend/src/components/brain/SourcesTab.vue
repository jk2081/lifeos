<template>
  <PageHead title="Brain" sub="Where information comes from. The Brain reads only what you switch on." />
  <div class="page-body flex max-w-6xl flex-col gap-6" data-brain-sources :data-loaded="loaded ? 1 : 0">
    <!-- issue 84: two groups. Channels are where a thing comes from, kinds are what it is; a thing passes its channel's rules first, then its kind's. -->
    <div class="flex flex-col gap-1" data-source-groups>
      <div class="inline-flex w-fit rounded-5 bg-surface-gray-2 p-0.5" role="tablist" aria-label="Sources">
        <button v-for="g in GROUPS" :key="g.value" type="button" role="tab" :aria-selected="group === g.value" class="min-h-9 rounded-4 px-3 text-sm focus-visible:focus-ring"
          :class="group === g.value ? 'bg-surface-base text-ink-gray-9 shadow-sm' : 'text-ink-gray-7'" :data-group="g.value" @click="setGroup(g.value)">{{ g.label }} <span class="tabular-nums text-ink-gray-6" :data-group-count="g.value">{{ g.count }}</span></button>
      </div>
      <p class="text-sm text-ink-gray-6">{{ group === 'kinds' ? 'What it is. After the rules of the channel it came by, a thing is read with the rules of its kind.' : 'Where it comes from. Everything passes its channel\'s rules first.' }}</p>
    </div>

    <section v-if="group === 'kinds'" class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3" data-kinds>
      <Card v-for="k in kinds" :key="k.key" class="relative flex flex-col gap-1.5 hover:bg-surface-gray-1" data-kind-card :data-kind="k.key" :data-week="k.this_week">
        <RouterLink :to="`/brain/sources/${k.key}`" class="absolute inset-0 rounded-5 focus-visible:focus-ring" :aria-label="`Open ${k.title}`" data-kind-open />
        <div class="text-base-medium text-ink-gray-9">{{ k.title }}</div>
        <div class="text-sm text-ink-gray-6">{{ k.line }}</div>
        <div class="flex flex-wrap items-center gap-x-2 text-sm text-ink-gray-8"><span data-kind-line>{{ k.this_week ? `${k.this_week} this week` : 'Nothing yet' }}</span><span class="text-ink-gray-5">{{ k.skill }} v{{ k.version }}</span></div>
      </Card>
    </section>

    <section v-if="group === 'channels'" class="flex flex-col gap-3" data-connected>
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-base-medium text-ink-gray-9">Connected · <span data-connected-count>{{ connected.length }}</span></h2>
        <Button v-if="writable" variant="solid" icon-left="lucide-plus" label="Add a source" data-add-source @click="toAddMore" />
      </div>
      <div v-if="connected.length" class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Card v-for="c in connected" :key="c.name" class="relative flex flex-col gap-2 hover:bg-surface-gray-1" data-source-card :data-system="c.system" :data-active="c.active" :data-week="c.this_week">
          <RouterLink :to="`/brain/sources/${c.system}`" class="absolute inset-0 rounded-5 focus-visible:focus-ring" :aria-label="`Open ${c.label}`" data-source-page />
          <div class="flex items-center gap-3">
            <span class="flex size-9 flex-none items-center justify-center rounded-4 bg-surface-gray-2 text-sm-medium text-ink-gray-8" aria-hidden="true">{{ c.icon }}</span>
            <div class="min-w-0 flex-1"><div class="truncate text-base-medium text-ink-gray-9">{{ c.label }}</div><div class="truncate text-sm text-ink-gray-6">{{ c.kind }}</div></div>
            <Switch class="relative" :model-value="!!c.active" :disabled="!writable" :label="c.active ? 'On' : 'Off'" data-source-switch @update:model-value="(v) => toggle(c, v)" />
            <Button class="relative" variant="ghost" icon="lucide-settings-2" :aria-label="`Settings of ${c.label}`" data-source-open @click="openSettings(c)" />
          </div>
          <p class="text-sm text-ink-gray-6" data-source-line>{{ c.line }}</p>
          <p class="text-sm text-ink-gray-8" data-processed-by>{{ c.processed_by }}</p>
          <p v-if="c.error" class="text-sm text-ink-red-4" data-source-error>{{ c.error }}</p>
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

    <section v-if="group === 'channels'" ref="more" class="flex flex-col gap-3" data-add-more>
      <h2 class="text-base-medium text-ink-gray-9">Add more <span class="text-sm font-normal text-ink-gray-6">One click each. Nothing is read until you switch it on.</span></h2>
      <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <div v-for="t in available" :key="t.system" class="relative flex flex-col items-center gap-0.5 rounded-5 border border-dashed border-outline-gray-2 px-3 py-4 text-center"
          :class="t.always_on ? '' : 'hover:bg-surface-gray-1'" data-source-tile :data-system="t.system" :data-always-on="t.always_on ? 1 : 0">
          <button v-if="writable && !t.always_on" type="button" class="absolute inset-0 rounded-5 focus-visible:focus-ring" :aria-label="t.system === 'gmail' ? 'Connect Gmail' : `Add ${t.label}`" data-tile-add @click="add(t)" />
          <span class="text-base-medium text-ink-gray-9">{{ t.label }}</span>
          <span class="text-sm text-ink-gray-6">{{ t.hint }}</span>
          <span v-if="t.processed_by" class="mt-0.5 text-xs text-ink-gray-5" data-processed-by>{{ t.processed_by }}</span>
          <Badge v-if="t.always_on" class="mt-1" theme="green" label="Always on" />
          <RouterLink :to="`/brain/sources/${t.system}`" class="relative mt-1 text-xs underline focus-visible:focus-ring" :aria-label="`Rules of ${t.label}`" data-tile-rules>Rules</RouterLink>
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
    <section v-if="group === 'channels'" class="flex flex-col gap-3" data-email-in :data-configured="emailIn.configured ? 1 : 0">
      <h2 class="text-base-medium text-ink-gray-9">Email-in address <span class="text-sm font-normal text-ink-gray-6">Optional. Forward an email to capture it.</span></h2>
      <Card class="flex flex-col gap-2">
        <p class="text-sm text-ink-gray-8" data-email-in-address>
          <template v-if="emailIn.address">Forward to <span class="text-base-medium">{{ emailIn.address }}</span></template>
          <template v-else>Not set up. Create a mailbox, add it as an incoming Email Account on the server, then choose it here.</template>
        </p>
        <p class="text-sm text-ink-gray-6">{{ emailIn.how_to }}</p>
        <div class="flex flex-col gap-1">
          <label class="text-sm text-ink-gray-7" for="email-in-senders">Allowed senders (your own addresses, one per line)</label>
          <Textarea id="email-in-senders" v-model="sendersText" class="w-full" :rows="3" placeholder="you@example.com" :disabled="!store.isAdmin" data-email-in-senders />
        </div>
        <div v-if="store.isAdmin" class="flex flex-col gap-1">
          <label class="text-sm text-ink-gray-7" for="email-in-account">Email Account (its name on the server)</label>
          <TextInput id="email-in-account" v-model="accountName" class="w-full" placeholder="Life OS" data-email-in-account />
        </div>
        <div v-if="store.isAdmin"><Button variant="solid" label="Save" data-email-in-save @click="saveEmailIn" /></div>
      </Card>
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
        <p class="text-sm text-ink-gray-6" data-settings-processed>{{ current.processed_by }}. {{ current.lands }}</p>
        <template v-if="current.system === 'gmail' && current.mailbox">
          <div data-gmail-label><FormControl v-model="draft.label_name" label="Only mail with this Gmail label" placeholder="Empty reads the Inbox, for example Life OS" :disabled="!writable" /></div>
          <div data-gmail-include><FormControl v-model="draft.always_include" type="textarea" :rows="2" label="Always include" placeholder="Senders or domains, one per line" :disabled="!writable" /></div>
          <div data-gmail-skip><FormControl v-model="draft.always_skip" type="textarea" :rows="2" label="Always skip" placeholder="Senders or domains, one per line" :disabled="!writable" /></div>
          <div data-gmail-sensitive><FormControl v-model="draft.always_sensitive" type="textarea" :rows="2" label="Always sensitive" placeholder="Their mail is marked sensitive" :disabled="!writable" /></div>
          <Switch v-model="draft.attach_files" :disabled="!writable" label="Keep attachments (up to 10 MB each)" data-gmail-attach />
          <p class="text-sm text-ink-gray-6">Life OS only reads this mailbox. It never marks, labels, moves or deletes mail. By default it skips Promotions, Social, Updates and Forums, mailing lists and no-reply senders.</p>
          <Button v-if="writable" variant="subtle" theme="red" label="Remove this mailbox" data-gmail-remove @click="removeGmail" />
        </template>
        <p v-else class="text-sm text-ink-gray-6">What this source sends without an area, goal or intent of its own is filed with these. No passwords or keys are kept here.</p>
      </div>
    </template>
  </Dialog>

  <Dialog v-model:open="gmailOpen" title="Connect Gmail" :actions="gmailSetup?.ready && writable ? [{ label: 'Continue to Google', variant: 'solid', onClick: connectGmail }] : []">
    <template #default>
      <div class="flex flex-col gap-2" data-gmail-connect>
        <p class="text-sm text-ink-gray-8">You sign in with Google in this browser. Life OS asks for <strong>read-only</strong> access to this mailbox and nothing else: it never marks, labels, moves, deletes or sends mail. Several mailboxes can be connected, one card each.</p>
        <p v-if="gmailSetup && !gmailSetup.ready" class="text-sm text-ink-amber-9" data-gmail-not-ready>Google sign-in is not set up yet. In Frappe, open Google Settings and enter the OAuth client (client ID and secret), then come back here.</p>
        <p v-else-if="gmailSetup" class="text-sm text-ink-gray-6">If Google says the redirect address does not match, add this one to the OAuth client in Google Cloud: <span class="break-all font-mono text-xs" data-gmail-redirect>{{ gmailSetup.redirect_uri }}</span></p>
      </div>
    </template>
  </Dialog>

  <Dialog v-model:open="otherOpen" title="Add another agent" :actions="[{ label: 'Add', variant: 'solid', onClick: addOther }]">
    <template #default>
      <div class="flex flex-col gap-2" data-other-agent>
        <FormControl v-model="otherName" label="Name" placeholder="For example Atlas" @keydown.enter="addOther" />
        <p class="text-sm text-ink-gray-6">The agent sends this as its source_system. It can bring things in once it has its own user and key (Settings, Members).</p>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
// Brain > Sources (issue 19): where information comes from, switched on one by one. A card for each connected source
// (a Life Connection), tiles for what can be added, and "Coming" tiles for what is not built yet. A source that is off
// makes the server refuse its captures; nothing it brought in is deleted.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dialog, FormControl, Switch, TextInput, Textarea } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import Pick from '@/components/Pick.vue'
import PageHead from '@/components/PageHead.vue'
import { tryCall } from '@/lib/api'
import { brainData } from '@/data/brain'
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
const gmailOpen = ref(false)
const gmailSetup = ref(null)
const emailIn = ref({})
const sendersText = ref('')
const accountName = ref('')
const route = useRoute()
const router = useRouter()
const channels = ref([])
const kinds = ref([])
const group = computed(() => (route.query.group === 'kinds' ? 'kinds' : 'channels'))
const GROUPS = computed(() => [{ value: 'channels', label: 'Channels', count: channels.value.length }, { value: 'kinds', label: 'Kinds', count: kinds.value.length }])
const setGroup = (v) => router.replace({ query: { ...route.query, group: v === 'channels' ? undefined : v } })

const goalOptions = computed(() => (lookups.goals || []).filter((g) => !draft.value.default_area || g.area === draft.value.default_area).map((g) => ({ value: g.name, label: g.title })))
const toAddMore = () => more.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
function lastReceived(c) {
  if (!c.last_received_on) return 'Nothing has arrived yet.'
  return `Last received: ${c.last_received_what ? c.last_received_what + ', ' : ''}${dateTime(c.last_received_on)}`
}
async function load() {
  loadLookups()
  const g = await tryCall(() => brainData.sourcePage.groups({ space: store.space }))
  if (g) { channels.value = g.channels; kinds.value = g.kinds }
  const res = await tryCall(() => brainData.connections.sources({ space: store.space }))
  if (res) {
    connected.value = res.connected; available.value = res.available; coming.value = res.coming
    emailIn.value = res.email_in || {}
    sendersText.value = (res.email_in?.senders || []).join('\n')
    if (store.isAdmin) accountName.value = (await tryCall(() => brainData.settings.get({ space: store.space })))?.settings?.email_in_account || ''
  }
  loaded.value = true
}
async function saveEmailIn() {
  const values = { email_in_senders: sendersText.value, email_in_account: accountName.value.trim() || null }
  if (await tryCall(() => brainData.settings.save({ values }), 'Saved.')) load()
}
async function toggle(c, on) {
  const res = await tryCall(() => brainData.connections.save({ name: c.name, active: on ? 1 : 0 }), on ? `${c.label} is on.` : `${c.label} is off. Nothing it brought in was deleted.`)
  if (res) Object.assign(c, { active: res.active, quiet: res.quiet })
}
function openSettings(c) {
  current.value = c
  draft.value = { active: !!c.active, default_intent: c.default_intent || 'Process', default_area: c.default_area || null, default_goal: c.default_goal || null,
    label_name: c.label_name || '', always_include: c.always_include || '', always_skip: c.always_skip || '', always_sensitive: c.always_sensitive || '', attach_files: !!c.attach_files }
  settingsOpen.value = true
}
async function save() {
  const d = draft.value
  const extra = current.value.system === 'gmail' && current.value.mailbox
    ? { label_name: d.label_name || '', always_include: d.always_include || '', always_skip: d.always_skip || '', always_sensitive: d.always_sensitive || '', attach_files: d.attach_files ? 1 : 0 } : {}
  const res = await tryCall(() => brainData.connections.save({ name: current.value.name, active: d.active ? 1 : 0, default_intent: d.default_intent, default_area: d.default_area || '', default_goal: d.default_goal || '', ...extra }), 'Saved.')
  if (!res) return
  settingsOpen.value = false
  await load()
}
async function add(t) {
  if (t.system === 'gmail') return openGmail()
  const res = await tryCall(() => brainData.connections.save({ space: store.space, system: t.system, active: 1 }), `${t.label} is on.`)
  if (!res) return
  await load()
  const c = connected.value.find((x) => x.system === t.system)
  if (c) openSettings(c)
}
async function openGmail() {
  gmailSetup.value = null
  gmailOpen.value = true
  gmailSetup.value = await tryCall(() => brainData.connections.gmail_setup())
}
async function connectGmail() {
  const res = await tryCall(() => brainData.connections.gmail_connect({ space: store.space, success_uri: '/life/brain/sources' }))
  if (res?.url) window.location.assign(res.url) // Google's own sign-in; Frappe brings the browser back here with ?gmail=<card>
}
async function finishGmail(name) {
  await router.replace({ path: route.path, query: { ...route.query, gmail: undefined } })
  const res = await tryCall(() => brainData.connections.gmail_finish({ name }), 'Gmail is connected. Life OS reads new mail every 15 minutes.')
  await load()
  const c = res && connected.value.find((x) => x.name === res.name)
  if (c) openSettings(c)
}
async function removeGmail() {
  const res = await tryCall(() => brainData.connections.gmail_remove({ name: current.value.name }), 'Mailbox removed. What it brought in stays.')
  if (!res) return
  settingsOpen.value = false
  await load()
}
async function addOther() {
  const system = otherName.value.trim().toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40)
  if (!system) return
  const res = await tryCall(() => brainData.connections.save({ space: store.space, system, label: otherName.value.trim(), active: 1 }), `${otherName.value.trim()} is on.`)
  if (!res) return
  otherOpen.value = false
  otherName.value = ''
  await load()
  const c = connected.value.find((x) => x.system === system)
  if (c) openSettings(c)
}
watch(() => store.space, async () => { await load(); if (route.query.gmail) await finishGmail(String(route.query.gmail)) }, { immediate: true })
</script>
