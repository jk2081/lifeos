<template>
  <PageHead title="Settings" :sub="`${store.space} · ${store.fullName || store.user}`">
    <TabButtons :model-value="colorScheme" :options="SCHEMES" aria-label="Theme" @update:model-value="setColorScheme" />
  </PageHead>
  <div v-if="d" class="page-body">
    <div class="cols">
      <div class="half">
        <section>
          <SectionHead>Spaces and members</SectionHead>
          <Card v-for="s in d.spaces" :key="s.name" class="mb-3">
            <div class="flex justify-between gap-2"><b class="text-base font-semibold text-ink-gray-9">{{ s.name }}</b><span class="text-sm text-ink-gray-6">owner {{ s.owner_user }}</span></div>
            <Row v-for="m in s.members" :key="m.user" class="!items-center">
              <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ m.full_name }}</div>
                <div class="break-words text-sm text-ink-gray-6">{{ m.user }} · {{ m.roles.join(', ') || 'no Life role' }}</div></div>
              <Select v-if="d.is_admin" class="w-24 shrink-0" :model-value="m.access" :options="['Write', 'Read']" :aria-label="`Access for ${m.user}`"
                @update:model-value="(v) => v && v !== m.access && member(s.name, m.user, v)" />
              <Badge v-else :label="m.access" />
              <Button v-if="d.is_admin && m.user !== s.owner_user" variant="ghost" label="Remove" @click="member(s.name, m.user, m.access, 1)" />
            </Row>
            <div v-if="d.is_admin" class="mt-2 flex gap-2">
              <TextInput v-model="newMember[s.name]" class="flex-1" placeholder="Email of an existing user" :aria-label="`Add a member to ${s.name}`" @keydown.enter="member(s.name, newMember[s.name])" />
              <Button label="Add" @click="member(s.name, newMember[s.name])" />
            </div>
          </Card>
          <div v-if="d.is_admin" class="flex flex-wrap gap-2">
            <TextInput v-model="newSpace.name" class="flex-[1_1_160px]" placeholder="New space, for example Anya" aria-label="New space name" />
            <TextInput v-model="newSpace.owner" class="flex-[1_1_160px]" placeholder="Owner's email (optional)" aria-label="Owner of the new space" />
            <Button label="Create space" @click="createSpace" />
          </div>
          <p class="mt-2 text-sm text-ink-gray-6">A person sees a record only if they are a member of its space. A new space starts with the areas Work, Personal &amp; Health, Money &amp; Legal and Family.</p>
        </section>

        <section>
          <SectionHead>Review and archive</SectionHead>
          <Card flush>
            <div class="divide-y divide-outline-gray-1">
              <SettingsRow title="Weekly review day">
                <Select v-model="d.settings.weekly_review_day" class="w-36" :options="DAYS" :disabled="!d.is_admin" />
              </SettingsRow>
              <SettingsRow title="Review time">
                <TimePicker v-model="d.settings.weekly_review_time" class="w-36" :disabled="!d.is_admin" />
              </SettingsRow>
              <SettingsRow title="Score target, %">
                <TextInput v-model.number="d.settings.score_target" class="w-36" type="number" min="1" max="100" :disabled="!d.is_admin" />
              </SettingsRow>
              <SettingsRow title="Archive after, days">
                <TextInput v-model.number="d.settings.archive_after_days" class="w-36" type="number" min="1" :disabled="!d.is_admin" />
              </SettingsRow>
              <SettingsRow title="Task is stale after, days">
                <TextInput v-model.number="d.settings.stale_task_days" class="w-36" type="number" min="1" :disabled="!d.is_admin" />
              </SettingsRow>
              <SettingsRow title="Default space">
                <Select v-model="d.settings.default_space" class="w-36" :options="d.spaces.map((s) => s.name)" :disabled="!d.is_admin" />
              </SettingsRow>
            </div>
            <div v-if="d.is_admin" class="flex justify-end border-t border-outline-gray-1 py-3"><Button variant="solid" label="Save" @click="saveSettings" /></div>
            <p v-else class="border-t border-outline-gray-1 py-3 text-sm text-ink-gray-6">Only the owner can change these.</p>
          </Card>
        </section>
      </div>

      <div class="half">
        <section v-for="l in LISTS" :key="l.kind">
          <SectionHead>{{ l.label }} <span class="font-normal text-ink-gray-6">in {{ d.space }}</span></SectionHead>
          <Card flush>
            <Row v-for="it in rows(l)" :key="it.name" class="!items-center">
              <div class="min-w-0 flex-1" :class="it.depth && 'pl-5'"><span class="break-words text-base-medium" :class="it.is_archived ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ it.title }}</span>
                <span v-if="it.relation" class="text-sm text-ink-gray-6"> · {{ it.relation }}</span></div>
              <div v-if="canWrite()" class="flex shrink-0 flex-wrap items-center justify-end">
                <Button v-if="l.ordered" variant="ghost" icon="lucide-arrow-up" :label="`Move ${it.title} up`" @click="moveUp(l, it)" />
                <Button variant="ghost" label="Rename" @click="rename(l, it)" />
                <Button v-if="l.kind === 'area'" variant="ghost" :label="it.is_archived ? 'Restore' : 'Archive'" @click="item(l, { name: it.name, is_archived: it.is_archived ? 0 : 1 })" />
                <Button variant="ghost" label="Remove" @click="remove(l, it)" />
              </div>
            </Row>
            <Empty v-if="!rows(l).length" :title="`No ${l.label.toLowerCase()} yet.`" :hint="l.hint" />
            <Row v-if="canWrite()" class="flex-wrap">
              <TextInput v-model="draft[l.kind]" class="min-w-32 flex-1" :placeholder="l.add" :aria-label="l.add" @keydown.enter="add(l)" />
              <Select v-if="l.kind === 'area'" v-model="draftParent" class="w-40" aria-label="Inside"
                :options="[{ label: 'Top level', value: '' }, ...d.areas.filter((x) => !x.parent_area).map((a) => ({ label: 'in ' + a.area_name, value: a.name }))]" />
              <Button label="Add" @click="add(l)" />
            </Row>
          </Card>
        </section>
        <p class="text-sm text-ink-gray-6">Habits here are the library of habits ever tracked. Which ones count in a month is set under Journal, Habits, Manage habits.</p>
      </div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
// A routed page, not frappe-ui's SettingsDialog: that family's panels and nav items are reka-ui tab parts that only work
// inside the dialog's own TabsRoot. SettingsRow is the one part with no such tie, and lays out the review settings.
import { Badge, Button, Select, SettingsRow, TabButtons, TextInput, TimePicker, dialog, useColorScheme } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import { api, tryCall } from '@/lib/api'
import { boot, canWrite, store } from '@/lib/store'
import { loadLookups } from '@/lib/lookups'

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const LISTS = [
  { kind: 'area', label: 'Areas', key: 'areas', field: 'area_name', ordered: true, add: 'New area', hint: 'Areas are your own filing headings.' },
  { kind: 'tag', label: 'Tags', key: 'tags', field: 'tag_name', add: 'New tag', hint: 'Tags are themes that cut across areas.' },
  { kind: 'dimension', label: 'Check-in dimensions', key: 'dimensions', field: 'dimension_name', ordered: true, add: 'New dimension', hint: 'The life dimensions scored in a check-in.' },
  { kind: 'habit', label: 'Habits', key: 'habits', field: 'title', add: 'New habit', hint: 'Habits you may track in a month.' },
  { kind: 'person', label: 'People', key: 'people', field: 'full_name', add: 'New person', hint: 'People you refer to: document holders, birthdays.' },
]
const SCHEMES = [{ label: 'System', value: 'system' }, { label: 'Light', value: 'light' }, { label: 'Dark', value: 'dark' }]
const { colorScheme, setColorScheme } = useColorScheme()
const d = ref(null)
const draft = reactive({})
const draftParent = ref('')
const newMember = reactive({})
const newSpace = reactive({ name: '', owner: '' })

function rows(l) {
  const list = d.value[l.key].map((x) => ({ ...x, title: x[l.field] }))
  if (l.kind !== 'area') return list
  const out = []
  for (const a of list.filter((x) => !x.parent_area)) {
    out.push(a)
    for (const c of list.filter((x) => x.parent_area === a.name)) out.push({ ...c, depth: 1 })
  }
  return out
}
async function load() {
  const res = await tryCall(() => api('settings.get', { space: store.space }))
  if (res) {
    if (res.settings.weekly_review_time) res.settings.weekly_review_time = String(res.settings.weekly_review_time).padStart(8, '0').slice(0, 5)
    d.value = res
  }
}
async function item(l, args, message) {
  const res = await tryCall(() => api('settings.save_item', { kind: l.kind, space: store.space, ...args }), message)
  if (res) {
    await load()
    loadLookups(true)
  }
  return res
}
async function add(l) {
  const title = (draft[l.kind] || '').trim()
  if (!title) return
  const extra = l.kind === 'area' ? { parent_area: draftParent.value, sort_order: d.value.areas.length + 1 } : l.ordered ? { sort_order: d.value[l.key].length + 1 } : {}
  if (await item(l, { title, ...extra })) draft[l.kind] = ''
}
function rename(l, it) {
  dialog.prompt({
    title: 'Rename', confirmLabel: 'Rename', fields: [{ name: 'title', label: 'Name', type: 'text', defaultValue: it.title, required: true }],
    onConfirm: async ({ values }) => {
      const title = (values.title || '').trim()
      if (title && title !== it.title) await item(l, { name: it.name, title }, 'Renamed.')
    },
  })
}
function remove(l, it) {
  dialog.danger({ title: 'Remove', message: `Remove “${it.title}”?`, confirmLabel: 'Remove', onConfirm: async () => { await item(l, { name: it.name, delete: 1 }, 'Removed.') } })
}
async function moveUp(l, it) {
  const peers = rows(l).filter((x) => (x.parent_area || '') === (it.parent_area || ''))
  const i = peers.findIndex((x) => x.name === it.name)
  if (i <= 0) return
  const order = peers.map((x) => x.name)
  order.splice(i - 1, 0, order.splice(i, 1)[0])
  for (let k = 0; k < order.length; k++) await api('settings.save_item', { kind: l.kind, name: order[k], sort_order: k + 1 })
  load()
}
async function saveSettings() {
  const s = { ...d.value.settings }
  if (s.weekly_review_time && s.weekly_review_time.length === 5) s.weekly_review_time += ':00'
  if (await tryCall(() => api('settings.save', { values: s }), 'Settings saved.')) boot()
}
async function member(space, user, access = 'Write', remove = 0) {
  if (!user || !user.trim()) return
  if (await tryCall(() => api('settings.set_member', { space, user: user.trim(), access, remove }), remove ? 'Removed.' : 'Saved.')) {
    newMember[space] = ''
    load()
  }
}
async function createSpace() {
  if (!newSpace.name.trim()) return
  if (await tryCall(() => api('settings.create_space', { space_name: newSpace.name, owner_user: newSpace.owner.trim() || undefined }), 'Space created.')) {
    newSpace.name = newSpace.owner = ''
    await boot()
    load()
  }
}
onMounted(load)
</script>
