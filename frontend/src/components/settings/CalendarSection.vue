<template>
  <div class="flex flex-col gap-4" data-settings-calendar>
    <Skeleton v-if="!s" class="h-32 w-full" />
    <template v-else>
      <Alert v-if="!s.configured" theme="amber" title="Google is not set up on this site"
        description="The owner enters the OAuth client ID and secret in Frappe's Google Settings. Until then the weekly review works without meetings."
        data-calendar-not-configured />
      <Card flush>
        <SettingRow label="Google Calendar" :help="s.fake ? 'This site reads a fixture calendar instead of Google (tests and acceptance).' :
          'Life OS reads your calendar to show last week\'s meetings in the weekly review. It writes only if you choose a calendar below. Life OS will change your calendar only when you ask: when you tell Chat an event is cancelled, or an agent you let change it does.'">
          <div class="flex items-center gap-2">
            <Badge :theme="s.connected ? 'green' : 'gray'" :label="s.connected ? 'Connected' : 'Not connected'" data-calendar-status />
            <Button v-if="!s.connected" variant="solid" label="Connect Google Calendar" :disabled="!s.configured" data-calendar-connect @click="connect" />
            <Button v-else-if="!s.fake" label="Disconnect" data-calendar-disconnect @click="disconnect" />
          </div>
        </SettingRow>
        <SettingRow v-if="s.connected" label="Last read" help="The last 21 days and the next 14, every hour and when the review opens.">
          <div class="flex items-center gap-2"><span class="text-base text-ink-gray-8" data-calendar-synced>{{ s.last_synced ? dateTime(s.last_synced) : 'Not yet' }}</span>
            <Button label="Read now" :loading="busy" data-calendar-sync @click="sync" /></div>
          <span v-if="s.error" class="text-sm text-ink-red-8">{{ s.error }}</span>
        </SettingRow>
        <SettingRow v-if="s.connected && cals.length" label="Calendars to read" help="Events from these calendars show in the weekly review, private to you.">
          <div class="flex flex-col items-start gap-1.5">
            <Checkbox v-for="c in cals" :key="c.id" :label="c.summary || c.id" :model-value="read.includes(c.id) || (c.primary && read.includes('primary'))"
              @update:model-value="(v) => toggle(c, v)" />
          </div>
        </SettingRow>
        <SettingRow v-if="s.connected && cals.length" label="Write to Google Calendar"
          help="Off by default. Events you accept and goal blocks from the weekly review are added to this calendar, private, with a link back here. Writing needs the Calendar scope on the Google client.">
          <select v-model="write" class="h-7 rounded border border-outline-gray-2 bg-surface-white px-2 text-base text-ink-gray-8" aria-label="Write to Google Calendar"
            data-calendar-write @change="saveWrite">
            <option value="">Off: nothing is written</option>
            <option v-for="c in cals" :key="c.id" :value="c.id">{{ c.summary || c.id }}</option>
          </select>
        </SettingRow>
      </Card>
      <Card flush>
        <SettingRow label="Your domains" help="Email domains that are yours, one per line. A meeting matters when someone from outside them attends for 30 minutes or more.">
          <div class="flex w-64 flex-col items-end gap-2 max-md:w-full max-md:items-start">
            <Textarea v-model="domains" class="w-full" :rows="3" aria-label="Your domains" :disabled="!store.isAdmin" data-setting="own_domains" />
            <Button v-if="store.isAdmin" label="Save" data-domains-save @click="saveDomains" />
          </div>
        </SettingRow>
      </Card>
    </template>
  </div>
</template>
<script setup>
// Settings > Me > Calendar (set 8, issue 31): Google Calendar through Frappe's own OAuth flow; read, and written to only when a calendar is chosen.
import { settingsData } from '@/data/settings'
import { onMounted, ref } from 'vue'
import { Alert, Badge, Button, Checkbox, Skeleton, Textarea, toast } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import SettingRow from './SettingRow.vue'
import { tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { dateTime } from '@/lib/dates'

const s = ref(null)
const cals = ref([])
const read = ref([])
const write = ref('')
const domains = ref('')
const busy = ref(false)
async function load() {
  s.value = await settingsData.gcal.state()
  domains.value = (s.value.domains || []).join('\n')
  read.value = s.value.read || []
  write.value = s.value.write || ''
  if (s.value.connected) {
    const got = await tryCall(() => settingsData.gcal.calendars())
    cals.value = got?.calendars || []
    write.value = got?.write || ''
  }
}
async function connect() {
  const out = await tryCall(() => settingsData.gcal.connect())
  if (out?.url) window.location.href = out.url
}
async function disconnect() {
  if (await tryCall(() => settingsData.gcal.disconnect(), 'Disconnected. Events already read stay.')) load()
}
async function sync() {
  busy.value = true
  const out = await tryCall(() => settingsData.gcal.sync())
  busy.value = false
  if (out) { s.value = { ...s.value, ...out }; toast.success(`${out.read} events read.`) }
}
async function toggle(c, on) {
  const ids = on ? [...new Set([...read.value, c.id])] : read.value.filter((x) => x !== c.id && !(c.primary && x === 'primary'))
  const out = await tryCall(() => settingsData.gcal.set_read({ ids }))
  if (out) read.value = out.read
}
async function saveWrite() {
  const out = await tryCall(() => settingsData.gcal.set_write({ calendar: write.value }), write.value ? 'Writing to that calendar.' : 'Writing is off.')
  if (out) write.value = out.write || ''
}
async function saveDomains() {
  await tryCall(() => settingsData.settings.save({ values: { own_domains: domains.value } }), 'Saved.')
}
onMounted(load)
</script>
