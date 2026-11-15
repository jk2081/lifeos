<template>
  <PageHead title="Settings" :sub="`${store.space} · ${store.fullName || store.user}`">
    <button class="bt s" type="button" @click="toggleColorScheme()">{{ resolvedColorScheme === 'dark' ? 'Light theme' : 'Dark theme' }}</button>
    <button v-if="colorScheme !== 'system'" class="bt t" type="button" @click="setColorScheme('system')">Follow the system</button>
  </PageHead>
  <div v-if="d" class="bd">
    <div class="cols">
      <div class="half">
        <section>
          <h2 class="sh">Spaces and members</h2>
          <div v-for="s in d.spaces" :key="s.name" class="cd" style="margin-bottom: 12px">
            <div style="display: flex; justify-content: space-between; gap: 8px"><b style="font-weight: 600">{{ s.name }}</b><span class="mt">owner {{ s.owner_user }}</span></div>
            <div v-for="m in s.members" :key="m.user" class="rw" style="align-items: center">
              <div class="grow"><div class="ttl">{{ m.full_name }}</div><div class="mt">{{ m.user }} · {{ m.roles.join(', ') || 'no Life role' }}</div></div>
              <select v-if="d.is_admin" class="inp" style="flex: none" :value="m.access" :aria-label="`Access for ${m.user}`" @change="member(s.name, m.user, $event.target.value)"><option>Write</option><option>Read</option></select>
              <span v-else class="pl n">{{ m.access }}</span>
              <button v-if="d.is_admin && m.user !== s.owner_user" class="bt t" type="button" @click="member(s.name, m.user, m.access, 1)">Remove</button>
            </div>
            <div v-if="d.is_admin" style="display: flex; gap: 8px; margin-top: 8px">
              <input v-model="newMember[s.name]" class="inp" style="flex: 1" placeholder="Email of an existing user" :aria-label="`Add a member to ${s.name}`" @keydown.enter="member(s.name, newMember[s.name])" />
              <button class="bt s" type="button" @click="member(s.name, newMember[s.name])">Add</button>
            </div>
          </div>
          <div v-if="d.is_admin" style="display: flex; gap: 8px; flex-wrap: wrap">
            <input v-model="newSpace.name" class="inp" style="flex: 1 1 160px" placeholder="New space, for example Anya" aria-label="New space name" />
            <input v-model="newSpace.owner" class="inp" style="flex: 1 1 160px" placeholder="Owner's email (optional)" aria-label="Owner of the new space" />
            <button class="bt s" type="button" @click="createSpace">Create space</button>
          </div>
          <p class="mt" style="margin: 8px 0 0">A person sees a record only if they are a member of its space. A new space starts with the areas Work, Personal &amp; Health, Money &amp; Legal and Family.</p>
        </section>

        <section>
          <h2 class="sh">Review and archive</h2>
          <div class="cd">
            <div class="formgrid">
              <div class="field"><label class="lbl" for="s-day">Weekly review day</label><select id="s-day" v-model="d.settings.weekly_review_day" class="inp" :disabled="!d.is_admin">
                <option v-for="x in DAYS" :key="x">{{ x }}</option></select></div>
              <div class="field"><label class="lbl" for="s-time">Review time</label><input id="s-time" v-model="d.settings.weekly_review_time" type="time" class="inp" :disabled="!d.is_admin" /></div>
              <div class="field"><label class="lbl" for="s-target">Score target, %</label><input id="s-target" v-model.number="d.settings.score_target" type="number" min="1" max="100" class="inp" :disabled="!d.is_admin" /></div>
              <div class="field"><label class="lbl" for="s-arch">Archive after, days</label><input id="s-arch" v-model.number="d.settings.archive_after_days" type="number" min="1" class="inp" :disabled="!d.is_admin" /></div>
              <div class="field"><label class="lbl" for="s-stale">Task is stale after, days</label><input id="s-stale" v-model.number="d.settings.stale_task_days" type="number" min="1" class="inp" :disabled="!d.is_admin" /></div>
              <div class="field"><label class="lbl" for="s-space">Default space</label><select id="s-space" v-model="d.settings.default_space" class="inp" :disabled="!d.is_admin">
                <option v-for="s in d.spaces" :key="s.name">{{ s.name }}</option></select></div>
            </div>
            <div v-if="d.is_admin" style="display: flex; justify-content: flex-end; margin-top: 12px"><button class="bt p" type="button" @click="saveSettings">Save</button></div>
            <p v-else class="mt" style="margin: 10px 0 0">Only the owner can change these.</p>
          </div>
        </section>
      </div>

      <div class="half">
        <section v-for="l in LISTS" :key="l.kind">
          <h2 class="sh">{{ l.label }} <span class="mt" style="font-weight: 400">in {{ d.space }}</span></h2>
          <div class="cd list">
            <div v-for="it in rows(l)" :key="it.name" class="rw" style="align-items: center">
              <div class="grow" :style="it.depth ? 'padding-left: 18px' : ''"><span class="ttl" :style="it.is_archived ? 'color: var(--ink-gray-6); text-decoration: line-through' : ''">{{ it.title }}</span>
                <span v-if="it.relation" class="mt"> · {{ it.relation }}</span></div>
              <template v-if="canWrite()">
                <button v-if="l.ordered" class="bt t ic" type="button" :aria-label="`Move ${it.title} up`" @click="moveUp(l, it)">↑</button>
                <button class="bt t" type="button" @click="rename(l, it)">Rename</button>
                <button v-if="l.kind === 'area'" class="bt t" type="button" @click="item(l, { name: it.name, is_archived: it.is_archived ? 0 : 1 })">{{ it.is_archived ? 'Restore' : 'Archive' }}</button>
                <button class="bt t" type="button" @click="remove(l, it)">Remove</button>
              </template>
            </div>
            <Empty v-if="!rows(l).length" :title="`No ${l.label.toLowerCase()} yet.`" :hint="l.hint" />
            <div v-if="canWrite()" class="rw">
              <input v-model="draft[l.kind]" class="inp" style="flex: 1" :placeholder="l.add" :aria-label="l.add" @keydown.enter="add(l)" />
              <select v-if="l.kind === 'area'" v-model="draftParent" class="inp" aria-label="Inside"><option value="">Top level</option>
                <option v-for="a in d.areas.filter((x) => !x.parent_area)" :key="a.name" :value="a.name">in {{ a.area_name }}</option></select>
              <button class="bt s" type="button" @click="add(l)">Add</button>
            </div>
          </div>
        </section>
        <p class="mt" style="margin: 0">Habits here are the library of habits ever tracked. Which ones count in a month is set under Journal, Habits, Manage habits.</p>
      </div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useColorScheme } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
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
const { colorScheme, resolvedColorScheme, setColorScheme, toggleColorScheme } = useColorScheme()
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
  const title = window.prompt('Name', it.title)
  if (title && title.trim() && title.trim() !== it.title) item(l, { name: it.name, title: title.trim() }, 'Renamed.')
}
function remove(l, it) {
  if (window.confirm(`Remove “${it.title}”?`)) item(l, { name: it.name, delete: 1 }, 'Removed.')
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
