<template>
  <PageHead title="Settings" :sub="store.fullName || store.user" />
  <div class="flex min-h-0 flex-1 max-md:block" data-settings>
    <!-- the menu: three groups. On a phone it is the first screen and a section opens full width with Back. -->
    <nav v-if="!phone || !section" class="w-60 flex-none overflow-y-auto border-r border-outline-gray-1 px-3 pb-10 pt-4 max-md:w-auto max-md:border-r-0 max-md:p-4" aria-label="Settings sections" data-settings-menu>
      <!-- wide screens: frappe-ui Tabs in its vertical form; a phone: the same groups as a list of rows, the first screen -->
      <Tabs v-if="!phone && d" vertical :model-value="section" @update:model-value="open">
        <TabList variant="ghost" class="w-full">
          <template v-for="g in groups" :key="g.key">
            <div class="px-2 pb-1 pt-4 text-sm-medium text-ink-gray-6 first:pt-0" :data-settings-group="g.key">{{ g.label }}</div>
            <div v-if="g.key === 'space' && d" class="mb-1.5 px-1" @keydown.stop>
              <Select :model-value="spaceSel" :options="d.spaces.map((s) => ({ label: s.name, value: s.name }))" aria-label="Space for these settings" data-settings-space
                @update:model-value="pickSpace" />
            </div>
            <TabTrigger v-for="it in g.items" :key="it.value" class="w-full justify-start" :value="it.value" :label="it.label" :data-section="it.value" />
          </template>
        </TabList>
      </Tabs>
      <template v-else>
        <section v-for="g in groups" :key="g.key" class="mb-4 flex flex-col gap-0.5">
          <div class="mb-1 text-sm-medium text-ink-gray-6" :data-settings-group="g.key">{{ g.label }}</div>
          <div v-if="g.key === 'space' && d" class="mb-1.5">
            <Select :model-value="spaceSel" :options="d.spaces.map((s) => ({ label: s.name, value: s.name }))" aria-label="Space for these settings" data-settings-space
              @update:model-value="pickSpace" />
          </div>
          <Button v-for="it in g.items" :key="it.value" class="!justify-start" size="lg" variant="ghost" icon-right="lucide-chevron-right" :label="it.label" :data-section="it.value"
            @click="open(it.value)" />
        </section>
      </template>
    </nav>

    <section v-if="section && (!phone || section)" class="min-w-0 flex-1 overflow-y-auto px-7 pb-16 pt-6 max-md:p-4" data-settings-section :data-current="section">
      <div class="flex max-w-[720px] flex-col gap-4">
        <Button v-if="phone" class="-ml-2 self-start" variant="ghost" icon-left="lucide-arrow-left" label="Settings" data-settings-back @click="open('')" />
        <div class="flex items-center gap-3">
          <h2 class="min-w-0 flex-1 text-lg-semibold text-ink-gray-9" data-section-title>{{ heading }}</h2>
          <Button v-if="listOf(section) && canEdit" variant="solid" icon-left="lucide-plus" :label="'New ' + listOf(section).one" data-new @click="newOpen = true" />
          <Button v-if="section === 'members' && memberSpace" variant="solid" icon-left="lucide-plus" label="Add member" data-add-member @click="addOpen = true" />
          <Button v-if="section === 'members'" label="New space" data-new-space @click="spaceOpen = true" />
        </div>
        <div v-if="!d" class="flex flex-col gap-3"><Skeleton v-for="i in 4" :key="i" class="h-10 w-full rounded-4" /></div>

        <!-- Me -->
        <Card v-else-if="section === 'appearance'" flush>
          <SettingRow label="Theme" help="Light, dark, or follow the system setting of this device.">
            <TabButtons :model-value="colorScheme" :options="SCHEMES" aria-label="Theme" data-theme-switch @update:model-value="setColorScheme" />
          </SettingRow>
        </Card>
        <Card v-else-if="section === 'default'" flush>
          <SettingRow label="Default space" help="The space the app opens in, and where new records go when no space is chosen." :error="errors.default_space">
            <Select class="w-44" :model-value="d.settings.default_space" :options="d.spaces.map((s) => s.name)" :disabled="!d.is_admin" data-setting="default_space"
              @update:model-value="(v) => setOne('default_space', v)" />
          </SettingRow>
          <p v-if="!d.is_admin" class="pb-3 text-sm text-ink-gray-6">Only the owner can change this.</p>
        </Card>
        <Card v-else-if="section === 'review'" flush>
          <SettingRow label="Review day" help="The day the weekly review is due. Today shows a reminder on that day." :error="errors.weekly_review_day">
            <Select class="w-44" :model-value="d.settings.weekly_review_day" :options="DAYS" :disabled="!d.is_admin" data-setting="weekly_review_day"
              @update:model-value="(v) => setOne('weekly_review_day', v)" />
          </SettingRow>
          <SettingRow label="Review time" help="The time of day the reminder appears." :error="errors.weekly_review_time">
            <TimePicker class="w-44" :model-value="d.settings.weekly_review_time" :disabled="!d.is_admin" data-setting="weekly_review_time"
              @update:model-value="(v) => setOne('weekly_review_time', v)" />
          </SettingRow>
          <SettingRow label="Score target" help="The 12 Week Year score, in per cent, that counts as a good week." :error="errors.score_target">
            <TextInput class="w-44" type="number" min="1" max="100" :model-value="d.settings.score_target" :disabled="!d.is_admin" data-setting="score_target"
              @change="(e) => setOne('score_target', Number(e.target.value))" />
          </SettingRow>
          <p v-if="!d.is_admin" class="pb-3 text-sm text-ink-gray-6">Only the owner can change these.</p>
        </Card>

        <!-- This space -->
        <template v-else-if="listOf(section)">
          <SettingsList :kind="listOf(section).kind" :rows="active(listOf(section))" :noun="listOf(section).noun" :hint="listOf(section).hint" :ordered="listOf(section).ordered"
            :writable="canEdit" :count-noun="listOf(section).countNoun" :link="listOf(section).link" @rename="rename" @reorder="reorder" @archive="askArchive" />
          <p class="text-sm text-ink-gray-6">{{ listOf(section).footer }}</p>
        </template>
        <Card v-else-if="section === 'archive'" flush>
          <SettingRow label="Archive after" help="Done and dropped tasks, and inbox items that are done, move to the Archive this many days after they were closed. Notes, documents, chats, journal pages and projects are never archived automatically."
            :error="errors.archive_after_days">
            <TextInput class="w-28" type="number" min="1" :model-value="d.settings.archive_after_days" :disabled="!d.is_admin" data-setting="archive_after_days"
              @change="(e) => setOne('archive_after_days', Number(e.target.value))"><template #suffix><span class="text-sm text-ink-gray-6">days</span></template></TextInput>
          </SettingRow>
          <SettingRow label="Task is stale after" help="An open task untouched for this many days is listed under Decide in the weekly review. Nothing is archived or changed by this." :error="errors.stale_task_days">
            <TextInput class="w-28" type="number" min="1" :model-value="d.settings.stale_task_days" :disabled="!d.is_admin" data-setting="stale_task_days"
              @change="(e) => setOne('stale_task_days', Number(e.target.value))"><template #suffix><span class="text-sm text-ink-gray-6">days</span></template></TextInput>
          </SettingRow>
          <p v-if="!d.is_admin" class="pb-3 text-sm text-ink-gray-6">Only the owner can change these.</p>
        </Card>
        <template v-else-if="section === 'archived'">
          <p class="text-sm text-ink-gray-6"><RouterLink class="text-ink-blue-8 hover:underline" to="/archive" data-archive-link>Archived records are on the Archive screen</RouterLink>.
            This list holds only the headings archived from Areas, Tags, Habits and Check-in dimensions.</p>
          <section v-for="l in LISTS" :key="l.kind" :data-archived-group="l.kind">
            <SectionHead :count="archived(l).length">{{ l.label }}</SectionHead>
            <Card flush>
              <div v-for="r in archived(l)" :key="r.name" class="flex min-h-11 flex-wrap items-center gap-2 border-b border-outline-gray-1 py-1.5 last:border-b-0" :data-archived-row="r.name">
                <div class="min-w-0 flex-1"><div class="break-words text-base text-ink-gray-9">{{ r.title }}<span v-if="r.parentTitle" class="text-ink-gray-6"> · under {{ r.parentTitle }}</span></div>
                  <div class="text-sm text-ink-gray-6">{{ r.archived_on ? 'Archived ' + short(r.archived_on, true) : 'Archived before the date was kept' }} · {{ r.count }} {{ r.count === 1 ? l.countNoun[0] : l.countNoun[1] }}</div></div>
                <Button v-if="canEdit" label="Restore" :data-restore="r.name" @click="askRestore(l, r)" />
              </div>
              <Empty v-if="!archived(l).length" :title="`No archived ${l.noun}.`" />
            </Card>
          </section>
        </template>

        <!-- Admin -->
        <template v-else-if="section === 'members'">
          <div class="flex gap-4 max-md:flex-col">
            <Select v-if="phone" :model-value="memberSpace" :options="d.spaces.map((s) => s.name)" aria-label="Space" @update:model-value="(v) => (memberSpace = v)" />
            <div v-else class="flex w-40 flex-none flex-col gap-0.5" data-member-spaces>
              <Button v-for="s in d.spaces" :key="s.name" class="!justify-start" :variant="s.name === memberSpace ? 'subtle' : 'ghost'" :label="s.name" :data-space="s.name" @click="memberSpace = s.name" />
            </div>
            <Card v-if="mSpace" flush class="min-w-0 flex-1" data-members>
              <div v-for="m in mSpace.members" :key="m.user" class="flex min-h-12 flex-wrap items-center gap-2.5 border-b border-outline-gray-1 py-2 last:border-b-0" :data-member="m.user">
                <Avatar size="md" :label="m.full_name" :image="m.image" />
                <div class="min-w-0 flex-1 basis-40"><div class="break-words text-base-medium text-ink-gray-9">{{ m.full_name }}</div><div class="break-all text-sm text-ink-gray-6">{{ m.user }}</div></div>
                <Badge v-if="m.is_owner" label="Owner" data-owner-badge />
                <Select v-else class="w-32" :model-value="m.access" :options="ACCESS" :aria-label="`Access for ${m.full_name}`" :data-access="m.user"
                  @update:model-value="(v) => v !== m.access && setMember(mSpace.name, m.user, v)" />
                <Dropdown v-if="!m.is_owner" :options="[{ label: 'Remove', icon: 'lucide-user-minus', theme: 'red', onClick: () => askRemove(mSpace, m) }]">
                  <Button variant="ghost" icon="lucide-ellipsis" :label="`More for ${m.full_name}`" :data-member-menu="m.user" /></Dropdown>
              </div>
              <Empty v-if="!mSpace.members.length" title="No members." />
            </Card>
          </div>
          <p class="text-sm text-ink-gray-6">A person sees a record only if they are a member of its space. Can view lets them read; Can edit lets them add and change records. Agents are under Agents.</p>
        </template>
        <template v-else-if="section === 'agents'">
          <Card flush data-agents>
            <div v-for="a in d.agents" :key="a.user" class="flex flex-col gap-2 border-b border-outline-gray-1 py-3 last:border-b-0" :data-agent="a.user">
              <div class="flex items-center gap-2.5"><Avatar size="md" :label="a.full_name" />
                <div class="min-w-0 flex-1"><div class="text-base-medium text-ink-gray-9">{{ a.full_name }}</div>
                  <div class="text-sm text-ink-gray-6">{{ a.last_filed ? 'Last filed something ' + dateTime(a.last_filed) : 'Has not filed anything yet' }}</div></div></div>
              <div v-for="r in a.spaces" :key="r.space" class="flex flex-wrap items-center gap-2 pl-10">
                <span class="min-w-24 flex-1 text-base text-ink-gray-8">{{ r.space }}</span>
                <Select class="w-36" :model-value="r.access || ''" :options="AGENT_ACCESS" :aria-label="`${a.full_name} in ${r.space}`" :data-agent-access="a.user + '|' + r.space"
                  @update:model-value="(v) => setAgent(r.space, a.user, v, r.access)" />
              </div>
            </div>
            <Empty v-if="!d.agents.length" title="No agents." hint="An agent is a user with the Life OS agent role and no other Life OS role. Create one in Frappe, then give it access here." />
          </Card>
          <section>
            <SectionHead>Vault</SectionHead>
            <Card flush>
              <SettingRow v-for="s in d.spaces" :key="s.name" :label="`Agents can open the Vault in ${s.name}`" help="Let agents open documents in this space's Vault. Off by default.">
                <Switch :model-value="!!s.agents_can_read_vault" :aria-label="`Agents can open the Vault in ${s.name}`" :data-vault-switch="s.name" @update:model-value="(v) => setVault(s, v)" />
              </SettingRow>
            </Card>
          </section>
          <p class="text-sm text-ink-gray-6">Keys for agents are made in Frappe, never on this screen.</p>
        </template>
      </div>
    </section>
  </div>

  <Dialog v-model:open="newOpen" :title="'New ' + (listOf(section)?.one || '')" size="sm"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Add', variant: 'solid', onClick: create }]">
    <div class="flex flex-col gap-3">
      <TextInput v-model="draft.title" :placeholder="listOf(section)?.placeholder" aria-label="Name" data-new-name @keydown.enter="create" />
      <Select v-if="section === 'areas'" v-model="draft.parent" :options="parentOptions" aria-label="Inside" />
    </div>
  </Dialog>
  <Dialog v-model:open="archiveOpen" :title="`Archive ${archiving?.row.title || ''}?`" size="md"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Archive', variant: 'solid', onClick: archive }]">
    <div class="flex flex-col gap-2 text-base text-ink-gray-8" data-archive-dialog>
      <template v-if="archiving?.l.kind === 'area'">
        <p>The area leaves the Areas screen, the sidebar and the area pickers.<template v-if="kidsOf(archiving.row).length"> Its {{ kidsOf(archiving.row).length }}
          sub-area{{ kidsOf(archiving.row).length === 1 ? ' is' : 's are' }} archived with it.</template></p>
        <p>Its records are not changed and stay where they are: still findable through search, the Timeline and their own screens.</p>
      </template>
      <p v-else>It leaves the {{ archiving?.l.kind === 'tag' ? 'tag pickers' : archiving?.l.kind === 'habit' ? 'habit pickers' : 'check-in form' }}. Past records that use it keep it.</p>
      <p class="text-sm text-ink-gray-6">Nothing is deleted. Restore it from Archived in Settings.</p>
    </div>
  </Dialog>
  <Dialog v-model:open="addOpen" :title="`Add a member to ${memberSpace}`" size="sm"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Add', variant: 'solid', onClick: addMember }]">
    <div class="flex flex-col gap-3" data-add-dialog>
      <LifeLink v-model="newMember.user" doctype="User" label="Person" placeholder="Search by name or email" />
      <Select v-model="newMember.access" :options="ACCESS" aria-label="Access" />
    </div>
  </Dialog>
  <Dialog v-model:open="spaceOpen" title="New space" size="sm"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Create space', variant: 'solid', onClick: createSpace }]">
    <div class="flex flex-col gap-3">
      <TextInput v-model="newSpace.name" label="Name" placeholder="For example Anya" />
      <LifeLink v-model="newSpace.owner" doctype="User" label="Owner" placeholder="You, unless you choose someone" />
      <p class="text-sm text-ink-gray-6">A new space starts with four areas: Work, Personal &amp; Health, Money &amp; Legal and Family. Rename or archive them later.</p>
    </div>
  </Dialog>
</template>
<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
// A routed page, not frappe-ui's SettingsDialog: that family's panels only work inside the dialog. The menu is frappe-ui
// Tabs in its vertical form, with the open section in the URL (tab=).
import { Avatar, Badge, Button, Dialog, Dropdown, Select, Skeleton, Switch, TabButtons, TabList, Tabs, TabTrigger, TextInput, TimePicker, dialog, toast, useColorScheme } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import SettingRow from '@/components/settings/SettingRow.vue'
import SettingsList from '@/components/settings/SettingsList.vue'
import LifeLink from '@/framework/LifeLink.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { boot, store } from '@/lib/store'
import { loadLookups } from '@/lib/lookups'
import { dateTime, short } from '@/lib/dates'

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const SCHEMES = [{ label: 'Light', value: 'light' }, { label: 'Dark', value: 'dark' }, { label: 'System', value: 'system' }]
const ACCESS = [{ label: 'Can view', value: 'Read' }, { label: 'Can edit', value: 'Write' }]
const AGENT_ACCESS = [{ label: 'No access', value: '' }, ...ACCESS]
const LISTS = [
  { kind: 'area', section: 'areas', label: 'Areas', one: 'area', noun: 'areas', key: 'areas', field: 'area_name', ordered: true, placeholder: 'For example Health',
    hint: 'Areas are your own filing headings.', countNoun: ['record', 'records'], link: (r) => ({ path: '/timeline', query: { area: r.name } }),
    footer: 'Drag the handle to reorder, or to the middle of another area to put it under that one. Alt and the arrow keys move a focused row.' },
  { kind: 'tag', section: 'tags', label: 'Tags', one: 'tag', noun: 'tags', key: 'tags', field: 'tag_name', placeholder: 'For example tax',
    hint: 'Tags are themes that cut across areas.', countNoun: ['tagged record', 'tagged records'], footer: 'Tags are listed by name.' },
  { kind: 'habit', section: 'habits', label: 'Habits', one: 'habit', noun: 'habits', key: 'habits', field: 'title', placeholder: 'For example Walk',
    hint: 'Habits you may track in a month.', countNoun: ['month', 'months'], footer: 'This is the library of habits ever tracked. Which ones count in a month is set under Journal, Habits, Manage habits.' },
  { kind: 'dimension', section: 'dimensions', label: 'Check-in dimensions', one: 'dimension', noun: 'dimensions', key: 'dimensions', field: 'dimension_name', ordered: true,
    placeholder: 'For example Health', hint: 'The life dimensions scored in a check-in.', countNoun: ['check-in', 'check-ins'], footer: 'Dimensions show in the check-in form in this order.' },
]
const route = useRoute()
const router = useRouter()
const phone = useMediaQuery('(max-width: 767px)')
const { colorScheme, setColorScheme } = useColorScheme()
const d = ref(null)
const errors = reactive({})
const newOpen = ref(false)
const draft = reactive({ title: '', parent: '' })
const archiveOpen = ref(false)
const archiving = ref(null)
const addOpen = ref(false)
const newMember = reactive({ user: null, access: 'Write' })
const spaceOpen = ref(false)
const newSpace = reactive({ name: '', owner: null })
const memberSpace = ref('')

const groups = computed(() => [
  { key: 'me', label: 'Me', items: [{ value: 'appearance', label: 'Appearance' }, { value: 'default', label: 'Default space' }, { value: 'review', label: 'Weekly review' }] },
  { key: 'space', label: 'This space', items: [{ value: 'areas', label: 'Areas' }, { value: 'tags', label: 'Tags' }, { value: 'habits', label: 'Habits' },
    { value: 'dimensions', label: 'Check-in dimensions' }, { value: 'archive', label: 'Archive rules' }, { value: 'archived', label: 'Archived' }] },
  ...(d.value?.is_admin ? [{ key: 'admin', label: 'Admin', items: [{ value: 'members', label: 'Spaces and members' }, { value: 'agents', label: 'Agents' }] }] : []),
])
const sections = computed(() => groups.value.flatMap((g) => g.items))
// the open section is tab= in the URL. On a wide screen the first section is the default; on a phone the menu is.
const ADMIN_ONLY = ['members', 'agents']
const section = computed(() => {
  const v = route.query.tab ? String(route.query.tab) : ''
  // an Admin section asked for before the settings have loaded is kept; once loaded, only a Life Admin has it
  if (sections.value.some((s) => s.value === v) || (!d.value && ADMIN_ONLY.includes(v))) return v
  return phone.value ? '' : 'appearance'
})
function open(v) {
  if (v === section.value) return
  router.push({ query: { ...route.query, tab: v && (phone.value || v !== 'appearance') ? v : undefined } })
}
// "This space": its own space picker, which does not change the space of the sidebar (space= in the URL)
const spaceSel = computed(() => (route.query.space ? String(route.query.space) : store.space))
const pickSpace = (v) => router.replace({ query: { ...route.query, space: v === store.space ? undefined : v } })
const spaceGroup = ['areas', 'tags', 'habits', 'dimensions', 'archive', 'archived']
const heading = computed(() => {
  const label = sections.value.find((s) => s.value === section.value)?.label || ''
  return spaceGroup.includes(section.value) ? `${label} in ${spaceSel.value}` : label
})
const canEdit = computed(() => d.value?.spaces.find((s) => s.name === spaceSel.value)?.access === 'Write')
const listOf = (sec) => LISTS.find((l) => l.section === sec)
const rowsOf = (l) => (d.value?.[l.key] || []).map((x) => ({ ...x, title: x[l.field] }))
const active = (l) => rowsOf(l).filter((x) => !x.is_archived)
function archived(l) {
  const all = rowsOf(l)
  return all.filter((x) => x.is_archived).map((x) => ({ ...x, parentTitle: x.parent_area ? all.find((p) => p.name === x.parent_area)?.title : null }))
}
const kidsOf = (r) => active(LISTS[0]).filter((x) => x.parent_area === r.name)
const parentOptions = computed(() => [{ label: 'Top level', value: '' }, ...active(LISTS[0]).filter((x) => !x.parent_area).map((a) => ({ label: 'Inside ' + a.title, value: a.name }))])
const mSpace = computed(() => d.value?.spaces.find((s) => s.name === memberSpace.value))

async function load() {
  const res = await tryCall(() => api('settings.get', { space: spaceSel.value }))
  if (!res) return
  if (res.settings.weekly_review_time) res.settings.weekly_review_time = String(res.settings.weekly_review_time).padStart(8, '0').slice(0, 5)
  d.value = res
  if (!res.spaces.some((s) => s.name === memberSpace.value)) memberSpace.value = res.spaces.find((s) => s.name === store.space)?.name || res.spaces[0]?.name || ''
}
// the sidebar, pickers and filters read the lists again at once
async function changed() {
  await load()
  await loadLookups(true)
  window.dispatchEvent(new CustomEvent('lifeos-areas-changed'))
}

// ---- plain settings: each saves on its own; an error shows under the field and the old value comes back ----
async function setOne(field, value) {
  const before = d.value.settings[field]
  if (value === before) return
  errors[field] = ''
  d.value.settings[field] = value
  let v = value
  if (field === 'weekly_review_time' && v && v.length === 5) v += ':00'
  try {
    await api('settings.save', { values: { [field]: v } })
    toast.success('Saved')
    if (field === 'default_space') boot()
  } catch (e) {
    errors[field] = errorText(e)
    d.value.settings[field] = before
  }
}

// ---- the four lists ----
async function rename(r, title) {
  const l = listOf(section.value)
  if (await tryCall(() => api('settings.save_item', { kind: l.kind, name: r.name, title }), 'Renamed')) changed()
}
async function reorder(names, parent) {
  const l = listOf(section.value)
  if (await tryCall(() => api('settings.reorder', { kind: l.kind, names, parent_area: l.kind === 'area' ? parent || '' : undefined }), 'Saved')) changed()
}
async function create() {
  const l = listOf(section.value)
  const title = draft.title.trim()
  if (!title) return
  const n = active(l).length
  const extra = l.kind === 'area' ? { parent_area: draft.parent, sort_order: n + 1 } : l.ordered ? { sort_order: n + 1 } : {}
  if (await tryCall(() => api('settings.save_item', { kind: l.kind, space: spaceSel.value, title, ...extra }), 'Added')) {
    newOpen.value = false
    draft.title = draft.parent = ''
    changed()
  }
}
function askArchive(r) {
  archiving.value = { l: listOf(section.value), row: r }
  archiveOpen.value = true
}
async function archive() {
  const { l, row } = archiving.value
  archiveOpen.value = false
  if (await tryCall(() => api('settings.save_item', { kind: l.kind, name: row.name, is_archived: 1 }), 'Archived')) changed()
}
function askRestore(l, r) {
  const kids = l.kind === 'area' ? archived(l).filter((x) => x.parent_area === r.name && (!r.archived_on || x.archived_on === r.archived_on)) : []
  if (!kids.length) return restore(l, r, 0)
  dialog.confirm({
    title: `Restore ${r.title}`, message: `${kids.length} sub-area${kids.length === 1 ? ' was' : 's were'} archived with it: ${kids.map((k) => k.title).join(', ')}. Restore ${kids.length === 1 ? 'it' : 'them'} too?`,
    actions: [{ label: 'Only this area', onClick: ({ close }) => { close(); return restore(l, r, 0) } },
      { label: 'Restore with sub-areas', variant: 'solid', onClick: ({ close }) => { close(); return restore(l, r, 1) } }],
  })
}
async function restore(l, r, withChildren) {
  if (await tryCall(() => api('settings.save_item', { kind: l.kind, name: r.name, is_archived: 0, with_children: withChildren }), 'Restored')) changed()
}

// ---- members, spaces and agents ----
async function setMember(space, user, access, remove = 0) {
  if (await tryCall(() => api('settings.set_member', { space, user, access, remove }), remove ? 'Removed' : 'Saved')) {
    await load()
    return true
  }
}
function askRemove(space, m) {
  dialog.danger({ title: `Remove ${m.full_name}?`, message: `${m.full_name} will no longer see anything in ${space.name}. Their records stay.`, confirmLabel: 'Remove',
    onConfirm: async () => { await setMember(space.name, m.user, m.access, 1) } })
}
async function addMember() {
  if (!newMember.user) return toast.error('Choose a person.')
  if (await setMember(memberSpace.value, newMember.user, newMember.access)) {
    addOpen.value = false
    newMember.user = null
  }
}
async function createSpace() {
  if (!newSpace.name.trim()) return toast.error('A name is needed.')
  if (await tryCall(() => api('settings.create_space', { space_name: newSpace.name, owner_user: newSpace.owner || undefined }), 'Space created')) {
    spaceOpen.value = false
    memberSpace.value = newSpace.name.trim()
    newSpace.name = ''
    newSpace.owner = null
    await boot()
    load()
  }
}
async function setAgent(space, user, access, before) {
  if ((access || '') === (before || '')) return
  await setMember(space, user, access || before || 'Read', access ? 0 : 1)
}
async function setVault(s, on) {
  if (await tryCall(() => api('settings.set_agent_vault', { space: s.name, allowed: on ? 1 : 0 }), 'Saved')) load()
}

watch(spaceSel, load, { immediate: true })
</script>
