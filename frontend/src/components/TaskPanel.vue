<template>
  <Panel :title="task ? 'Task' : 'Loading…'" :sub="task && sub" @close="$emit('close')">
    <template v-if="task">
      <div class="field"><label class="lbl" for="tp-title">Title</label>
        <input id="tp-title" v-model="task.title" class="inp" :disabled="!writable" @change="save({ title: task.title })" /></div>
      <div class="formgrid">
        <div class="field"><label class="lbl" for="tp-status">Status</label>
          <select id="tp-status" :value="task.status" class="inp" :disabled="!writable" @change="setStatus($event.target.value)">
            <option v-for="s in ['Open', 'Doing', 'Waiting', 'Done', 'Dropped', 'Carried']" :key="s">{{ s }}</option>
          </select></div>
        <div class="field"><label class="lbl" for="tp-pri">Priority</label>
          <select id="tp-pri" v-model="task.priority" class="inp" :disabled="!writable" @change="save({ priority: task.priority })">
            <option :value="null">—</option><option v-for="p in PRIORITIES" :key="p">{{ p }}</option>
          </select></div>
        <div class="field"><label class="lbl" for="tp-due">Due date</label>
          <input id="tp-due" v-model="task.due_date" type="date" class="inp" :disabled="!writable" @change="save({ due_date: task.due_date })" /></div>
      </div>
      <div v-if="task.status === 'Waiting' || askWaiting" class="field"><label class="lbl" for="tp-wait">Waiting on</label>
        <input id="tp-wait" ref="waitInput" v-model="task.waiting_on" class="inp" placeholder="Who or what is this waiting on?" :disabled="!writable"
          @change="askWaiting ? setStatus('Waiting') : save({ waiting_on: task.waiting_on })" /></div>
      <div class="field"><span class="lbl">Filed under</span>
        <div class="chips">
          <Pick :model-value="task.area" :options="areaOptions()" placeholder="area" :disabled="!writable" @update:model-value="(v) => save({ area: v })" />
          <Pick :model-value="task.project" :options="projectOptions" prefix="Project: " placeholder="project" :disabled="!writable" @update:model-value="(v) => save({ project: v })" />
          <span v-for="a in task.also_in" :key="a" class="ch sm">also in {{ areaName(a) }}
            <a v-if="writable" href="#" aria-label="Remove" @click.prevent="save({ also_in: task.also_in.filter((x) => x !== a) })">×</a></span>
          <Pick :model-value="null" :options="areaOptions().filter((o) => o.value !== task.area && !task.also_in.includes(o.value))" placeholder="also in"
            :clearable="false" :disabled="!writable" @update:model-value="(v) => save({ also_in: [...task.also_in, v] })" />
          <span v-for="t in task.tag_ids" :key="t" class="ch sm">#{{ tagName(t) }}
            <a v-if="writable" href="#" aria-label="Remove" @click.prevent="save({ tag_ids: task.tag_ids.filter((x) => x !== t) })">×</a></span>
          <Pick v-if="lookups.tags.length" :model-value="null" :options="lookups.tags.filter((t) => !task.tag_ids.includes(t.name)).map((t) => ({ value: t.name, label: '#' + t.tag_name }))"
            placeholder="tag" :clearable="false" :disabled="!writable" @update:model-value="(v) => save({ tag_ids: [...task.tag_ids, v] })" />
        </div>
      </div>
      <div class="field"><label class="lbl" for="tp-goal">12 Week Year goal</label>
        <select id="tp-goal" v-model="task.goal" class="inp" :disabled="!writable" @change="save({ goal: task.goal })">
          <option :value="null">—</option><option v-for="g in lookups.goals" :key="g.name" :value="g.name">{{ g.title }}</option>
        </select></div>
      <div class="field"><label class="lbl" for="tp-notes">Notes</label>
        <textarea id="tp-notes" v-model="task.notes_md" class="inp" rows="5" placeholder="Markdown. Link a record with [[Title]]." :disabled="!writable" @change="save({ notes_md: task.notes_md })"></textarea></div>
      <div class="mt">
        <div v-if="task.inbox_item">From <RouterLink :to="`/inbox/${task.inbox_item}`">{{ task.source_title || 'an inbox item' }}</RouterLink></div>
        <div v-if="task.source_url"><a :href="task.source_url" target="_blank" rel="noopener noreferrer">Source link</a></div>
        <div v-if="task.month_plan">In the month plan {{ task.month_plan.split('-').slice(-2).join('-') }}</div>
        <div>Created {{ short(task.creation, true) }}<span v-if="task.completed_on"> · closed {{ short(task.completed_on, true) }}</span></div>
      </div>
      <div v-if="writable" class="chips">
        <button v-if="OPEN.includes(task.status)" class="bt s" type="button" @click="carry">Carry to next month →</button>
        <button class="bt s" type="button" @click="archive">{{ task.is_archived ? 'Restore' : 'Archive' }}</button>
        <button v-if="!isAgent" class="bt t" type="button" style="color: var(--r-ink)" @click="remove">Delete</button>
      </div>
      <Backlinks doctype="Life Task" :name="task.name" :reload="reloadKey" />
    </template>
  </Panel>
</template>
<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { toast } from 'frappe-ui'
import Panel from './Panel.vue'
import Pick from './Pick.vue'
import Backlinks from './Backlinks.vue'
import { api, db, errorText, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { OPEN, PRIORITIES } from '@/lib/tasks'
import { areaName, areaOptions, loadLookups, lookups } from '@/lib/lookups'

const props = defineProps({ name: String })
const emit = defineEmits(['close', 'changed'])
const task = ref(null)
const askWaiting = ref(false)
const waitInput = ref(null)
const reloadKey = ref(0)
const isAgent = false
const writable = computed(() => store.spaces.find((s) => s.name === task.value?.space)?.access === 'Write')
const sub = computed(() => [task.value.area_name, task.value.project_title].filter(Boolean).join(' · ') || 'Unfiled')
const tagName = (id) => lookups.tags.find((t) => t.name === id)?.tag_name || id
const projectOptions = computed(() => {
  const areas = [task.value.area, ...task.value.also_in]
  return lookups.projects.filter((p) => areas.includes(p.area)).map((p) => ({ value: p.name, label: p.title }))
})

async function load() {
  task.value = await tryCall(() => api('tasks.get', { task: props.name }))
  if (!task.value) emit('close')
}
async function save(values) {
  try {
    task.value = await api('tasks.update', { task: props.name, values })
    emit('changed', task.value)
  } catch (e) {
    toast.error(errorText(e))
    load()
  }
}
async function setStatus(status) {
  if (status === 'Waiting' && !(task.value.waiting_on || '').trim()) {
    askWaiting.value = true
    await nextTick()
    waitInput.value?.focus()
    toast.info('Say who or what this is waiting on.')
    return
  }
  try {
    task.value = await api('tasks.set_status', { task: props.name, status, waiting_on: task.value.waiting_on })
    askWaiting.value = false
    emit('changed', task.value)
  } catch (e) {
    toast.error(errorText(e))
    load()
  }
}
async function carry() {
  const res = await tryCall(() => api('tasks.carry_forward', { task: props.name }))
  if (res) {
    toast.success(`Carried into ${res.month}/${res.year}.`)
    emit('changed', null)
    emit('close')
  }
}
async function archive() {
  const res = await tryCall(() => api('archive.set', { doctype: 'Life Task', name: props.name, archived: task.value.is_archived ? 0 : 1 }),
    task.value.is_archived ? 'Restored.' : 'Archived.')
  if (res) {
    emit('changed', null)
    emit('close')
  }
}
async function remove() {
  if (!window.confirm('Delete this task for good?')) return
  if ((await tryCall(() => db.delete('Life Task', props.name), 'Deleted.')) !== undefined) {
    emit('changed', null)
    emit('close')
  }
}
onMounted(() => {
  loadLookups()
  load()
})
</script>
