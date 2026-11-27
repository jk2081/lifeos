<template>
  <Skeleton v-if="!m" class="h-48 w-full" />
  <div v-else class="flex flex-col gap-5" data-meeting :data-meeting-name="m.name">
    <section>
      <h3 class="mb-1 text-base-medium text-ink-gray-9">Linked to this meeting · {{ m.linked.length }}</h3>
      <div v-for="l in m.linked" :key="l.link" class="flex items-center gap-2 border-b border-outline-gray-1 py-2 last:border-b-0" data-meeting-linked :data-how="l.how">
        <Badge size="sm" theme="gray" :label="l.kind" />
        <span v-if="l.sensitive" class="lucide-lock size-3.5 shrink-0 text-ink-gray-6" role="img" aria-label="Sensitive" data-sensitive-lock />
        <span class="min-w-0 flex-1 truncate text-base text-ink-gray-8">{{ l.title }}</span>
        <Button variant="ghost" size="sm" label="Open" @click="openRef(l.ref)" />
        <Button variant="ghost" size="sm" icon="lucide-unlink" label="Unlink" data-meeting-unlink @click="act('meeting_link', { event: m.name, unlink: l.link })" />
      </div>
      <p v-if="!m.linked.length" class="text-sm text-ink-gray-6">Nothing captured during or after this meeting is linked yet.</p>
      <Dropdown v-if="m.candidates.length" class="mt-2" :options="m.candidates.map((c) => ({ label: `${c.kind}: ${c.title}`, onClick: () => act('meeting_link', { event: m.name, doctype: c.doctype, name: c.name }) }))">
        <Button size="sm" icon-left="lucide-link" label="Link a record" data-meeting-link-add />
      </Dropdown>
    </section>
    <section>
      <h3 class="mb-1 text-base-medium text-ink-gray-9">Follow-ups found · {{ m.followups.length }}</h3>
      <FindingRow v-for="f in m.followups" :key="f.name" :f="f" @act="(i) => finding(f, i)" />
      <p v-if="!m.followups.length" class="text-sm text-ink-gray-6">{{ m.ai ? 'None found in what was linked.' : 'The assistant is not set up, so follow-ups are not read.' }}</p>
    </section>
    <section class="flex flex-col gap-2">
      <h3 class="text-base-medium text-ink-gray-9">Anything to plan from this meeting?</h3>
      <TextInput v-model="line" placeholder="Type a task. Enter adds it, linked to this meeting." aria-label="A task from this meeting" data-meeting-plan
        @keydown.enter.prevent="plan" />
      <div class="flex items-center gap-2 text-sm text-ink-gray-7"><span>Will link to goal:</span>
        <Select v-model="goal" class="w-64" :options="[{ label: 'No goal', value: '' }, ...m.goals]" aria-label="Goal" data-meeting-goal /></div>
    </section>
    <section class="flex items-center gap-2">
      <Switch :model-value="m.matters" label="This meeting matters" data-meeting-matters @update:model-value="(v) => act('meeting_mark', { event: m.name, matters: v ? 1 : 0 })" />
      <span class="text-sm text-ink-gray-6">{{ m.set_by === 'Owner' ? 'set by you' : 'by the rule' }}</span>
    </section>
  </div>
    <div v-if="m" class="flex flex-wrap items-center gap-2 border-t border-outline-gray-1 pt-3" data-meeting-footer>
      <Button icon="lucide-arrow-left" label="Previous meeting" :disabled="!m.prev" data-meeting-prev @click="swapTop('meeting:' + m.prev)" />
      <Button icon="lucide-arrow-right" label="Next meeting" :disabled="!m.next" data-meeting-next @click="swapTop('meeting:' + m.next)" />
      <span class="flex-1 text-sm text-ink-gray-6 max-md:hidden">← → for the previous or next meeting</span>
      <Button variant="solid" :label="m.done ? 'Done' : 'Done with this meeting'" data-meeting-done @click="done" />
    </div>
</template>
<script setup>
// A meeting opened from the weekly review's Library tab (board 29), as a layer of the Drawer (issue 146): what is linked, the follow-ups found, a line that
// becomes a task linked to the meeting (and the goal shown), the "matters" switch, and the previous and next meeting that matters with the arrow keys.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Badge, Button, Dropdown, Select, Skeleton, Switch, TextInput } from 'frappe-ui'
import FindingRow from '@/components/review/FindingRow.vue'
import { closePane, openRef, swapTop } from '@/lib/pane'
import { weeklyAct, weeklyRead } from '@/lib/review'
import { store } from '@/lib/store'
import { short, time, weekday } from '@/lib/dates'

const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const m = ref(null)
const line = ref('')
const goal = ref('')
const when = computed(() => m.value ? `${weekday(m.value.start, 3)} ${short(m.value.start)}, ${time(m.value.start)}${m.value.end ? ' to ' + time(m.value.end) : ''}` : '')
// the others at the meeting (not the owner himself)
const people = computed(() => (m.value?.attendees || []).filter((a) => a.email !== store.user).slice(0, 4).map((a) => a.name || a.email).join(', '))

async function load() {
  try {
    m.value = await weeklyRead('meeting', { event: props.name })
  } catch (e) {
    return emit('missing')
  }
  line.value = ''
  goal.value = m.value.goal || ''
  emit('meta', { title: m.value.title, kind: 'Meeting', sub: [when.value, people.value, m.value.area_name].filter(Boolean).join(' · ') })
}
// a change: the meeting is read again, and the review behind the Drawer follows
async function act(method, args, ok) {
  if (!(await weeklyAct(method, args, ok))) return false
  await load()
  emit('changed')
  return true
}
async function finding(f, index) {
  const a = f.actions.find((x) => x.index === index)
  // looking is not acting: these open another meeting or the record, and the finding stays
  if (a?.kind === 'open_meetings') return a.events?.length ? swapTop('meeting:' + a.events[0]) : undefined
  if (a?.kind === 'open_record' && a.ref) return openRef(a.ref)
  await act('finding_act', { insight: f.name, index, goal: m.value.goal || undefined }, a?.kind === 'make_task' ? 'Task made.' : undefined)
}
async function plan() {
  if (!line.value.trim()) return
  const title = line.value
  line.value = ''
  await act('meeting_plan', { event: m.value.name, title, goal: goal.value || undefined }, 'Task made, linked to this meeting.')
}
async function done() {
  if (!(await weeklyAct('meeting_done', { event: m.value.name }))) return
  emit('changed')
  if (m.value.next) swapTop('meeting:' + m.value.next)
  else closePane()
}
function key(e) {
  if (!m.value || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return
  if (e.key === 'ArrowLeft' && m.value.prev) swapTop('meeting:' + m.value.prev)
  if (e.key === 'ArrowRight' && m.value.next) swapTop('meeting:' + m.value.next)
}
watch(() => props.name, load, { immediate: true })
onMounted(() => window.addEventListener('keydown', key))
onBeforeUnmount(() => window.removeEventListener('keydown', key))
</script>
