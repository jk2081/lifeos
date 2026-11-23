<template>
  <Drawer :open="!!event" name="meeting" :title="m?.title || 'Meeting'" @close="emit('close')">
    <template #sub>
      <span v-if="m" data-meeting-sub>{{ when }}<template v-if="people"> · {{ people }}</template><template v-if="m.area_name"> · {{ m.area_name }}</template></span>
    </template>
    <Skeleton v-if="!m" class="h-48 w-full" />
    <div v-else class="flex flex-col gap-5" data-meeting :data-meeting-name="m.name">
      <section>
        <h3 class="mb-1 text-base-medium text-ink-gray-9">Linked to this meeting · {{ m.linked.length }}</h3>
        <div v-for="l in m.linked" :key="l.link" class="flex items-center gap-2 border-b border-outline-gray-1 py-2 last:border-b-0" data-meeting-linked :data-how="l.how">
          <Badge size="sm" theme="gray" :label="l.kind" />
          <span v-if="l.sensitive" class="lucide-lock size-3.5 shrink-0 text-ink-gray-6" role="img" aria-label="Sensitive" data-sensitive-lock />
          <span class="min-w-0 flex-1 truncate text-base text-ink-gray-8">{{ l.title }}</span>
          <Button variant="ghost" size="sm" label="Open" @click="openRef(l.ref)" />
          <Button variant="ghost" size="sm" icon="lucide-unlink" label="Unlink" data-meeting-unlink @click="emit('act', 'meeting_link', { event: m.name, unlink: l.link })" />
        </div>
        <p v-if="!m.linked.length" class="text-sm text-ink-gray-6">Nothing captured during or after this meeting is linked yet.</p>
        <Dropdown v-if="m.candidates.length" class="mt-2" :options="m.candidates.map((c) => ({ label: `${c.kind}: ${c.title}`, onClick: () => emit('act', 'meeting_link', { event: m.name, doctype: c.doctype, name: c.name }) }))">
          <Button size="sm" icon-left="lucide-link" label="Link a record" data-meeting-link-add />
        </Dropdown>
      </section>
      <section>
        <h3 class="mb-1 text-base-medium text-ink-gray-9">Follow-ups found · {{ m.followups.length }}</h3>
        <FindingRow v-for="f in m.followups" :key="f.name" :f="f" @act="(i) => emit('finding', f, i)" />
        <p v-if="!m.followups.length" class="text-sm text-ink-gray-6">{{ ai ? 'None found in what was linked.' : 'The assistant is not set up, so follow-ups are not read.' }}</p>
      </section>
      <section class="flex flex-col gap-2">
        <h3 class="text-base-medium text-ink-gray-9">Anything to plan from this meeting?</h3>
        <TextInput v-model="line" placeholder="Type a task. Enter adds it, linked to this meeting." aria-label="A task from this meeting" data-meeting-plan
          @keydown.enter.prevent="plan" />
        <div class="flex items-center gap-2 text-sm text-ink-gray-7"><span>Will link to goal:</span>
          <Select v-model="goal" class="w-64" :options="[{ label: 'No goal', value: '' }, ...m.goals]" aria-label="Goal" data-meeting-goal /></div>
      </section>
      <section class="flex items-center gap-2">
        <Switch :model-value="m.matters" label="This meeting matters" data-meeting-matters @update:model-value="(v) => emit('act', 'meeting_mark', { event: m.name, matters: v ? 1 : 0 })" />
        <span class="text-sm text-ink-gray-6">{{ m.set_by === 'Owner' ? 'set by you' : 'by the rule' }}</span>
      </section>
    </div>
    <template #footer>
      <Button icon="lucide-arrow-left" label="Previous meeting" :disabled="!m?.prev" data-meeting-prev @click="emit('go', m.prev)" />
      <Button icon="lucide-arrow-right" label="Next meeting" :disabled="!m?.next" data-meeting-next @click="emit('go', m.next)" />
      <span class="flex-1 text-sm text-ink-gray-6 max-md:hidden">← → for the previous or next meeting</span>
      <Button variant="solid" :label="m?.done ? 'Done' : 'Done with this meeting'" data-meeting-done @click="emit('done', m)" />
    </template>
  </Drawer>
</template>
<script setup>
// A meeting opened from Library (board 29): what is linked, the follow-ups found, a line that becomes a task linked to the
// meeting (and the goal shown), and the previous and next meeting that matters with ← and →.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Badge, Button, Dropdown, Select, Skeleton, Switch, TextInput } from 'frappe-ui'
import Drawer from '@/components/ui/Drawer.vue'
import FindingRow from '@/components/review/FindingRow.vue'
import { openRef } from '@/lib/pane'
import { store } from '@/lib/store'
import { short, time, weekday } from '@/lib/dates'

const props = defineProps({ event: String, m: Object, ai: Boolean })
const emit = defineEmits(['close', 'act', 'finding', 'go', 'done', 'plan'])
const line = ref('')
const goal = ref('')
watch(() => props.m?.name, () => { line.value = ''; goal.value = props.m?.goal || '' })
const when = computed(() => props.m ? `${weekday(props.m.start, 3)} ${short(props.m.start)}, ${time(props.m.start)}${props.m.end ? ' to ' + time(props.m.end) : ''}` : '')
// the others at the meeting (not the owner himself)
const people = computed(() => (props.m?.attendees || []).filter((a) => a.email !== store.user).slice(0, 4).map((a) => a.name || a.email).join(', '))
function plan() {
  if (!line.value.trim()) return
  emit('plan', { event: props.m.name, title: line.value, goal: goal.value || undefined })
  line.value = ''
}
function key(e) {
  if (!props.event || !props.m || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return
  if (e.key === 'ArrowLeft' && props.m.prev) emit('go', props.m.prev)
  if (e.key === 'ArrowRight' && props.m.next) emit('go', props.m.next)
}
onMounted(() => window.addEventListener('keydown', key))
onBeforeUnmount(() => window.removeEventListener('keydown', key))
</script>
