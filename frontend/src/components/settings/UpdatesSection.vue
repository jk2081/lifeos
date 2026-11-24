<template>
  <div class="flex flex-col gap-4" data-updates>
    <Skeleton v-if="!s" class="h-32 w-full" />
    <template v-else>
      <div v-if="!s.runner.alive" class="flex flex-col gap-2" data-updates-setup>
        <Alert theme="amber" title="The updater is not set up on this server"
          description="Updating runs outside the web app, from a crontab line that runs every minute. On the server, as the user that owns the bench, run the command below once." />
        <code class="block select-all break-all rounded bg-surface-gray-2 px-2 py-1.5 text-sm text-ink-gray-8" data-updates-command>{{ s.runner.setup_command }}</code>
      </div>
      <Card flush>
        <SettingRow label="Installed" :help="s.installed ? (s.installed.title || '') : 'Not read yet. Choose Check now.'">
          <span v-if="s.installed" class="text-base tabular-nums text-ink-gray-8" data-updates-installed>{{ s.installed.short }} · {{ shortDate(s.installed.date) }}</span>
          <span v-else class="text-base text-ink-gray-6" data-updates-installed>Not checked</span>
        </SettingRow>
        <SettingRow label="Available" :help="availableHelp">
          <div class="flex items-center gap-2">
            <Button label="Check now" :loading="checking" data-updates-check @click="check" />
            <Button v-if="s.runner.alive && s.available" variant="solid" label="Update now" :disabled="s.busy" :loading="requesting" data-updates-now @click="update" />
          </div>
        </SettingRow>
        <p v-if="s.error" class="pb-3 text-sm text-ink-red-8" data-updates-error>{{ s.error }}</p>
      </Card>
      <section v-if="s.available" data-updates-changes>
        <SectionHead>{{ s.available.changes.length }} change{{ s.available.changes.length === 1 ? '' : 's' }} waiting<template v-if="s.available.migrations"> · includes migrations</template></SectionHead>
        <Card flush>
          <Row v-for="c in s.available.changes" :key="c.commit"><span class="min-w-0 flex-1 text-base text-ink-gray-8">{{ c.title }}</span>
            <span class="text-sm tabular-nums text-ink-gray-6">{{ c.short }}</span></Row>
        </Card>
      </section>
      <section>
        <SectionHead>Past updates</SectionHead>
        <Empty v-if="!s.history.length" title="No updates yet" hint="When you update from here, each one is listed with its result and log." data-updates-empty />
        <Card v-else flush data-updates-history>
          <div v-for="u in s.history" :key="u.name" class="border-b border-outline-gray-1 px-3 py-2.5 last:border-b-0" :data-update="u.name">
            <div class="flex items-center gap-2">
              <Badge :theme="THEME[u.status]" :label="u.status" data-update-status />
              <span class="min-w-0 flex-1 text-base text-ink-gray-8">{{ (u.from_commit || '').slice(0, 7) }} → {{ u.to_commit.slice(0, 7) }}</span>
              <span class="text-sm text-ink-gray-6">{{ dateTime(u.requested_on) }}</span>
              <Button v-if="u.log" variant="ghost" size="sm" :label="open === u.name ? 'Hide log' : 'Log'" @click="open = open === u.name ? '' : u.name" />
            </div>
            <pre v-if="open === u.name" class="mt-2 overflow-x-auto whitespace-pre-wrap rounded bg-surface-gray-2 p-2 text-xs text-ink-gray-8" data-update-log>{{ u.log }}</pre>
          </div>
        </Card>
      </section>
    </template>
  </div>
</template>
<script setup>
// Settings > Advanced > Updates (issue 103): installed and available commits, Check now, Update now, and the history of updates.
// The page only reads state and records a request; the runner on the server does the work.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Alert, Badge, Button, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import SettingRow from './SettingRow.vue'
import { settingsData } from '@/data/settings'
import { tryCall } from '@/lib/api'
import { dateTime, short } from '@/lib/dates'

const THEME = { Queued: 'gray', Running: 'blue', Done: 'green', Failed: 'red', 'Rolled back': 'amber' }
const s = ref(null)
const open = ref('')
const checking = ref(false)
const requesting = ref(false)
let timer = null
const shortDate = (d) => (d ? short(String(d).slice(0, 10), true) : '')
const availableHelp = computed(() => {
  if (!s.value?.installed) return 'Choose Check now to look at the repository.'
  if (s.value.available) return `${s.value.available.short} on ${s.value.branch}, ${shortDate(s.value.available.date)}`
  return s.value.checked_at ? `Nothing newer on ${s.value.branch}. Checked ${dateTime(s.value.checked_at)}.` : 'Not checked yet.'
})
async function load() {
  s.value = await tryCall(() => settingsData.updates.get())
  // an update that is waiting or running is watched
  clearTimeout(timer)
  if (s.value?.busy) timer = setTimeout(load, 5000)
}
async function check() {
  checking.value = true
  const before = s.value?.checked_at
  await tryCall(() => settingsData.updates.check_now())
  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 2000))
    s.value = await tryCall(() => settingsData.updates.get())
    if (s.value?.checked_at !== before) break
  }
  checking.value = false
}
async function update() {
  requesting.value = true
  const out = await tryCall(() => settingsData.updates.request_update(), 'Update queued. The server starts it within a minute.')
  requesting.value = false
  if (out) { s.value = out; await load() }
}
onMounted(load)
onBeforeUnmount(() => clearTimeout(timer))
</script>
