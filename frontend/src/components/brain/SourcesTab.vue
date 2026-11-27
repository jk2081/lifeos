<template>
  <PageHead title="Brain" sub="Where information comes from. The Brain reads only what you switch on." />
  <div class="page-body flex max-w-6xl flex-col gap-6" data-brain-sources :data-loaded="loaded ? 1 : 0">
    <!-- issue 101: one list of the sources in use. Capture is always on, so it is a line, not a card. -->
    <p v-if="capture" class="text-sm text-ink-gray-7" data-capture-line>
      <span class="text-sm-medium text-ink-gray-9">Capture</span> · always on · {{ capture.line }}<template v-if="capture.this_week"> · {{ capture.this_week }} this week</template> · <RouterLink class="underline focus-visible:focus-ring" to="/brain/sources/upload" data-capture-rules>Rules</RouterLink>
    </p>

    <section class="flex flex-col gap-3" data-connected>
      <EmptyState v-if="loaded && !sources.some((c) => c.connected !== 0)" line="Nothing is connected yet. Things you capture yourself are always read. Connect a source below and what it brings in is filed for you." data-sources-empty />
      <div v-if="sources.length" class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Card v-for="c in sources" :key="c.name || c.system" class="relative flex flex-col gap-2" :class="c.connected === 0 ? '' : 'hover:bg-surface-gray-1'" data-source-card
          :data-system="c.system" :data-state="c.state" :data-active="c.active" :data-week="c.this_week">
          <RouterLink v-if="c.name && !c.pending" :to="`/brain/sources/${c.system}`" class="absolute inset-0 rounded-5 focus-visible:focus-ring" :aria-label="`Open ${c.label}`" data-source-page />
          <div class="flex items-center gap-3">
            <span class="flex size-9 flex-none items-center justify-center rounded-4 bg-surface-gray-2 text-sm-medium text-ink-gray-8" aria-hidden="true">{{ c.icon }}</span>
            <div class="min-w-0 flex-1"><div class="truncate text-base-medium text-ink-gray-9" data-source-label>{{ c.label }}<template v-if="c.mailbox && c.mailbox !== c.label"> · {{ c.mailbox }}</template></div><div class="truncate text-sm text-ink-gray-6">{{ c.kind }}</div></div>
            <Badge v-if="c.state === 'Waiting'" theme="amber" label="Waiting" data-source-state />
            <Button v-else-if="c.connected === 0" class="relative" variant="solid" :label="`Connect`" :disabled="!writable" :aria-label="`Connect ${c.label}`" data-source-connect @click="connect(c)" />
            <Switch v-else class="relative" :model-value="!!c.active" :disabled="!writable" :label="c.active ? 'On' : 'Off'" data-source-switch @update:model-value="(v) => toggle(c, v)" />
            <Button v-if="c.name && !c.pending" class="relative" variant="ghost" icon="lucide-settings-2" :aria-label="`Settings of ${c.label}`" data-source-open @click="openSettings(c)" />
          </div>
          <p class="text-sm text-ink-gray-6" data-source-line>{{ c.line }}</p>
          <p v-if="c.pending" class="text-sm text-ink-gray-6" data-switch-note>Finish signing in first.</p>
          <p class="text-sm text-ink-gray-8" data-processed-by>{{ c.processed_by }}</p>
          <p v-if="c.error" class="text-sm text-ink-red-4" data-source-error>{{ c.error }}</p>
          <div v-if="c.pending && c.redirect_uri && c.error" class="flex flex-col gap-1" data-pending-address>
            <span class="text-sm text-ink-gray-6">Add this address in {{ c.system === 'microsoft' ? 'Azure' : 'Google Cloud' }} › Credentials › your OAuth client › Authorized redirect URIs:</span>
            <span class="flex flex-wrap items-center gap-2"><span class="break-all font-mono text-xs text-ink-gray-8" data-redirect-address>{{ c.redirect_uri }}</span>
              <Button size="sm" label="Copy" data-redirect-copy @click="copy(c.redirect_uri)" /></span>
          </div>
          <p v-if="c.active && c.quiet && !c.pending" class="text-sm text-ink-amber-9" data-source-quiet>{{ c.error ? 'The last read failed.' : 'Nothing has arrived for a while.' }}</p>
          <div v-if="c.pending && writable" class="relative flex flex-wrap gap-2">
            <Button v-if="c.error" variant="solid" label="Try again" data-source-retry @click="retry(c)" />
            <Button variant="subtle" theme="red" label="Remove" data-source-remove @click="removePending(c)" />
          </div>
          <div v-if="c.add_another && writable" class="relative"><Button variant="subtle" :label="`Add another ${c.system === 'microsoft' ? 'Microsoft inbox' : 'Gmail'}`" icon-left="lucide-plus" data-add-another @click="openGmail(c.system === 'microsoft')" /></div>
        </Card>
      </div>
    </section>

    <section v-if="more" class="flex flex-col gap-3" data-more-sources>
      <SectionHead>Not built yet <span class="text-sm font-normal text-ink-gray-6">Shown because more sources are switched on for this site.</span></SectionHead>
      <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <div v-for="t in coming" :key="t.system" class="flex flex-col items-center gap-0.5 rounded-5 border border-dashed border-outline-gray-2 px-3 py-4 text-center opacity-80"
          data-source-tile data-tile-coming :data-system="t.system" aria-disabled="true">
          <span class="text-base-medium text-ink-gray-9">{{ t.label }}</span><span class="text-sm text-ink-gray-6">{{ t.hint }}</span>
          <Badge class="mt-1" theme="gray" label="Coming" />
        </div>
      </div>
      <div v-if="writable"><Button label="Add another agent" icon-left="lucide-plus" data-tile-other @click="otherOpen = true" /></div>
    </section>

    <section class="flex flex-col gap-3" data-email-in :data-configured="emailIn.configured ? 1 : 0">
      <SectionHead>Email-in address <span class="text-sm font-normal text-ink-gray-6">Optional. Forward an email to capture it.</span></SectionHead>
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
        <template v-if="MAIL.includes(current.system) && current.mailbox">
          <div data-gmail-label><FormControl v-model="draft.label_name" label="The daily digest reads only mail with this label" placeholder="Empty reads the Inbox, for example Life OS" :disabled="!writable" /></div>
          <div data-gmail-include><FormControl v-model="draft.always_include" type="textarea" :rows="2" label="Always include" placeholder="Senders or domains, one per line" :disabled="!writable" /></div>
          <div data-gmail-skip><FormControl v-model="draft.always_skip" type="textarea" :rows="2" label="Always skip" placeholder="Senders or domains, one per line" :disabled="!writable" /></div>
          <div data-gmail-sensitive><FormControl v-model="draft.always_sensitive" type="textarea" :rows="2" label="Always sensitive" placeholder="Their mail is marked sensitive" :disabled="!writable" /></div>
          <p class="text-sm text-ink-gray-6">Mail is not copied into Life OS. Each morning a digest lists the mail from real people (it skips Promotions, Social, Updates and Forums, mailing lists and no-reply senders), and Ask and your agent search this mailbox live when you ask. Nothing is sent, archived or labelled except at your request, or with your OK to what your agent suggests. Nothing is deleted.</p>
          <Button v-if="writable" variant="subtle" theme="red" label="Remove this mailbox" data-gmail-remove @click="removeGmail" />
        </template>
        <p v-else class="text-sm text-ink-gray-6">What this source sends without an area, goal or intent of its own is filed with these. No passwords or keys are kept here.</p>
      </div>
    </template>
  </Dialog>

  <Dialog v-model:open="gmailOpen" :title="`Connect ${microsoft ? 'Microsoft' : 'Gmail'}`" :actions="gmailSetup?.ready && writable ? [{ label: needsAddress ? `I've added it` : `Continue to ${microsoft ? 'Microsoft' : 'Google'}`, variant: 'solid', onClick: connectGmail }] : []">
    <template #default>
      <div class="flex flex-col gap-2" data-gmail-connect>
        <p class="text-sm text-ink-gray-8">You sign in with {{ microsoft ? 'Microsoft (Outlook or Microsoft 365)' : 'Google' }} in this browser. Life OS asks to <strong>read</strong> this mailbox when you or your agent search it, and to send, draft, archive or label mail{{ microsoft ? '' : ' and change your calendar' }} when you ask your agent to or approve what it suggests. It copies none of your mail and never deletes any. Several mailboxes can be connected, one card each.</p>
        <p v-if="gmailSetup && !gmailSetup.ready && microsoft" class="text-sm text-ink-amber-9" data-gmail-not-ready>Microsoft sign-in is not set up yet. Put the Azure app's client ID and secret in the site config (docs/MICROSOFT.md), then come back here.</p>
        <p v-else-if="gmailSetup && !gmailSetup.ready" class="text-sm text-ink-amber-9" data-gmail-not-ready>Google sign-in is not set up yet. In Frappe, open Google Settings and enter the OAuth client (client ID and secret), then come back here.</p>
        <!-- the first time through an address, it has to be allowed in the provider's console before it will send the person back -->
        <div v-else-if="needsAddress" class="flex flex-col gap-2" data-redirect-step>
          <p class="text-sm text-ink-gray-8">Add this address in {{ microsoft ? 'Azure' : 'Google Cloud' }} › {{ microsoft ? 'App registrations › your app › Authentication › Redirect URIs' : 'Credentials › your OAuth client › Authorized redirect URIs' }}:</p>
          <div class="flex flex-wrap items-center gap-2"><span class="break-all font-mono text-xs text-ink-gray-9" data-gmail-redirect>{{ gmailSetup.redirect_uri }}</span>
            <Button size="sm" label="Copy" data-redirect-copy @click="copy(gmailSetup.redirect_uri)" /></div>
          <a :href="gmailSetup.console_url" target="_blank" rel="noopener" class="w-fit text-sm text-ink-blue-8 underline focus-visible:focus-ring" data-redirect-link>Open {{ microsoft ? 'the Azure portal' : 'Google Cloud credentials' }}</a>
        </div>
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
import EmptyState from '@/components/ui/EmptyState.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
// Brain > Sources (issue 19, simplified in 101): one list of the sources in use, each with its state (On, Off, Waiting) and its Connect or settings
// button. A source that is off makes the server refuse its captures; nothing it brought in is deleted.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dialog, FormControl, Switch, TextInput, Textarea, toast } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Pick from '@/components/Pick.vue'
import PageHead from '@/components/PageHead.vue'
import { tryCall } from '@/lib/api'
import { brainData } from '@/data/brain'
import { areaOptions, loadLookups, lookups } from '@/lib/lookups'
import { dateTime } from '@/lib/dates'
import { canWrite, store } from '@/lib/store'

const INTENTS = [{ label: 'Process', value: 'Process' }, { label: 'Add to wiki', value: 'Add to wiki' }, { label: 'Just keep', value: 'Just keep' }]
const writable = computed(() => canWrite() && !store.isAgent)
const sources = ref([])
const capture = ref(null)
const more = ref(false)
const coming = ref([])
const loaded = ref(false)
const settingsOpen = ref(false)
const current = ref(null)
const draft = ref({})
const otherOpen = ref(false)
const otherName = ref('')
const gmailOpen = ref(false)
const gmailSetup = ref(null)
const microsoft = ref(false)
const needsAddress = computed(() => !!gmailSetup.value?.ready && !gmailSetup.value.confirmed)
const MAIL = ['gmail', 'microsoft']
const emailIn = ref({})
const sendersText = ref('')
const accountName = ref('')
const route = useRoute()
const router = useRouter()

const goalOptions = computed(() => (lookups.goals || []).filter((g) => !draft.value.default_area || g.area === draft.value.default_area).map((g) => ({ value: g.name, label: g.title })))
function lastReceived(c) {
  if (!c.last_received_on) return 'Nothing has arrived yet.'
  return `Last received: ${c.last_received_what ? c.last_received_what + ', ' : ''}${dateTime(c.last_received_on)}`
}
async function load() {
  loadLookups()
  const res = await tryCall(() => brainData.connections.sources({ space: store.space }))
  if (res) {
    sources.value = res.sources; capture.value = res.capture; more.value = !!res.more; coming.value = res.coming
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
  if (res) Object.assign(c, { active: res.active, quiet: res.quiet, state: res.active ? 'On' : 'Off' })
}
function openSettings(c) {
  current.value = c
  draft.value = { active: !!c.active, default_intent: c.default_intent || 'Process', default_area: c.default_area || null, default_goal: c.default_goal || null,
    label_name: c.label_name || '', always_include: c.always_include || '', always_skip: c.always_skip || '', always_sensitive: c.always_sensitive || '' }
  settingsOpen.value = true
}
async function save() {
  const d = draft.value
  const extra = MAIL.includes(current.value.system) && current.value.mailbox
    ? { label_name: d.label_name || '', always_include: d.always_include || '', always_skip: d.always_skip || '', always_sensitive: d.always_sensitive || '' } : {}
  const res = await tryCall(() => brainData.connections.save({ name: current.value.name, active: d.active ? 1 : 0, default_intent: d.default_intent, default_area: d.default_area || '', default_goal: d.default_goal || '', ...extra }), 'Saved.')
  if (!res) return
  settingsOpen.value = false
  await load()
}
async function connect(t) {
  if (MAIL.includes(t.system)) return openGmail(t.system === 'microsoft')
  const res = await tryCall(() => brainData.connections.save({ space: store.space, system: t.system, active: 1 }), `${t.label} is on.`)
  if (!res) return
  if (t.system === 'google-calendar') return router.push({ path: '/settings', query: { tab: 'calendar' } }) // the sign-in is Settings > Calendar
  await load()
  const c = sources.value.find((x) => x.system === t.system)
  if (c) openSettings(c)
}
async function copy(text) {
  try { await navigator.clipboard.writeText(text) } catch (e) { /* the address stays on screen to select */ }
  toast.success('Copied.')
}
async function removePending(c) {
  if (await tryCall(() => brainData.connections.gmail_remove({ name: c.name }), 'Removed.')) await load()
}
async function retry(c) {
  if (await tryCall(() => brainData.connections.gmail_remove({ name: c.name }))) { await load(); openGmail(c.system === 'microsoft') }
}
async function openGmail(isMicrosoft = false) {
  microsoft.value = isMicrosoft
  gmailSetup.value = null
  gmailOpen.value = true
  gmailSetup.value = await tryCall(() => (isMicrosoft ? brainData.connections.microsoft_setup() : brainData.connections.gmail_setup()))
}
async function connectGmail() {
  const args = { space: store.space, success_uri: '/life/brain/sources' }
  const res = await tryCall(() => (microsoft.value ? brainData.connections.microsoft_connect(args) : brainData.connections.gmail_connect(args)))
  if (res?.url) window.location.assign(res.url) // Google's own sign-in; Frappe brings the browser back here with ?gmail=<card>
}
async function finishGmail(name, isMicrosoft = false) {
  await router.replace({ path: route.path, query: { ...route.query, gmail: undefined, microsoft: undefined } })
  const res = await tryCall(() => (isMicrosoft ? brainData.connections.microsoft_finish({ name }) : brainData.connections.gmail_finish({ name })), `${isMicrosoft ? 'Microsoft' : 'Gmail'} is connected. Life OS searches it when asked and lists its mail in the daily digest.`)
  await load()
  const c = res && sources.value.find((x) => x.name === res.name)
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
  const c = sources.value.find((x) => x.system === system)
  if (c) openSettings(c)
}
watch(() => store.space, async () => { await load(); if (route.query.gmail) await finishGmail(String(route.query.gmail)); if (route.query.microsoft) await finishGmail(String(route.query.microsoft), true) }, { immediate: true })
</script>
