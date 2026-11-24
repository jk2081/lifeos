<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-library>
    <div class="page-body !gap-4">
      <div class="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 class="text-xl-semibold text-ink-gray-9">What came in, and what it means</h2>
          <p class="text-sm text-ink-gray-6">Last week's meetings, everything captured, and what the assistant noticed across it.</p>
        </div>
        <div v-if="d?.strip" class="flex items-center gap-4 text-sm text-ink-gray-7 max-md:hidden">
          <span class="flex items-center gap-1.5"><span class="size-2 rounded-full bg-surface-green-7" aria-hidden="true" />notes or follow-ups linked</span>
          <span class="flex items-center gap-1.5"><span class="size-2 rounded-full border-2 border-outline-amber-6" aria-hidden="true" />meeting that matters, nothing captured</span>
        </div>
      </div>
      <Skeleton v-if="!d" class="h-80 w-full" />
      <template v-else>
        <CalendarStrip :strip="d.strip" :open="meetingName" @open="openMeeting" @list="listOpen = true" />
        <Card v-if="d.unused_pins?.length" class="flex flex-col gap-2" data-unused-pins>
          <h3 class="text-base-medium text-ink-gray-9">Pinned, not opened for a month</h3>
          <div v-for="p in d.unused_pins" :key="p.doctype + p.name" class="flex items-center justify-between gap-2" data-unused-pin :data-name="p.name">
            <span class="min-w-0 truncate text-base text-ink-gray-8">{{ p.title }}</span>
            <Button size="sm" :label="`Unpin ${p.title}`" data-unpin @click="dropPin(p)" />
          </div>
        </Card>
        <div class="grid grid-cols-[minmax(0,1fr)] items-start gap-4 md:grid-cols-[minmax(280px,1fr)_2fr]">
          <Card class="flex flex-col gap-1" data-came-in>
            <h3 class="mb-1 text-base-medium text-ink-gray-9">Came in · {{ d.came_in.total }}</h3>
            <div v-for="c in d.came_in.rows" :key="c.key" class="flex items-center justify-between border-b border-outline-gray-1 py-1.5 text-base last:border-b-0" :data-came-in-row="c.key">
              <span class="text-ink-gray-8">{{ c.label }}</span>
              <Button v-if="c.drawer" variant="ghost" size="sm" class="!text-ink-blue-8 tabular-nums" :label="String(c.n)" :aria-label="`${c.n} ${c.label}`"
                data-meetings-door :data-count-n="c.n" @click="listOpen = true" />
              <CountLink v-else class="font-semibold" :count="{ n: c.n, to: c.to, label: c.label }" :data-door="'review-came-' + c.key" />
            </div>
          </Card>
          <Card class="flex min-w-0 flex-col" data-revelations>
            <div class="flex flex-wrap items-baseline justify-between gap-2">
              <h3 class="text-base-medium text-ink-gray-9" data-revelations-count :data-n="d.revelations.length">Revelations · {{ revelationsLabel }}</h3>
              <span class="text-sm text-ink-gray-6">What the assistant noticed. Act or dismiss each.</span>
            </div>
            <FindingRow v-for="f in d.revelations" :key="f.name" :f="f" @act="(i) => act(f, i)" />
            <p v-if="!d.revelations.length" class="py-3 text-sm text-ink-gray-6" data-revelations-empty>Nothing left to look at.</p>
            <p v-if="!d.ai" class="mt-2 text-sm text-ink-gray-6" data-revelations-no-key>The assistant is not set up, so revelations are limited.</p>
          </Card>
        </div>
      </template>
    </div>
    <MeetingDrawer :event="meetingName" :m="meeting" :ai="d?.ai" @close="closeMeeting" @go="openMeeting" @act="meetingAct" @finding="act" @done="doneMeeting" @plan="plan" />
    <Drawer :open="listOpen" name="meetings" title="Meetings that matter" sub="In this review's period." @close="listOpen = false">
      <div v-for="m in list" :key="m.name" class="flex items-center gap-2 border-b border-outline-gray-1 py-2 last:border-b-0" data-meetings-row>
        <span class="size-2 flex-none rounded-full" :class="m.mark === 'linked' ? 'bg-surface-green-7' : 'border-2 border-outline-amber-6'" aria-hidden="true" />
        <div class="min-w-0 flex-1"><div class="truncate text-base text-ink-gray-9">{{ m.title }}</div>
          <div class="text-sm text-ink-gray-6">{{ dateTime(m.start) }} · {{ m.attendees.join(', ') }}</div></div>
        <Button size="sm" label="Open" @click="listOpen = false; openMeeting(m.name)" />
      </div>
      <p v-if="!list.length" class="text-sm text-ink-gray-6">No meetings that matter in this period.</p>
    </Drawer>
    <ReviewFooter label="Next: Tasks" :line="footerLine" @next="emit('go', 'tasks')" />
  </div>
</template>
<script setup>
// Tab 1, Library (boards 28 and 29): the calendar strip, what came in by source, and the revelations.
// Library never blocks: its footer button is always "Next: Tasks".
import { computed, onMounted, ref, watch } from 'vue'
import { Button, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import CountLink from '@/components/ui/CountLink.vue'
import Drawer from '@/components/ui/Drawer.vue'
import { unpin } from '@/lib/pins'
import CalendarStrip from '@/components/review/CalendarStrip.vue'
import FindingRow from '@/components/review/FindingRow.vue'
import MeetingDrawer from '@/components/review/MeetingDrawer.vue'
import ReviewFooter from '@/components/review/ReviewFooter.vue'
import { useReview } from '@/lib/review'
import { dateTime } from '@/lib/dates'
import { openRef } from '@/lib/pane'
import { useRouter } from 'vue-router'

const emit = defineEmits(['go'])
const r = useReview()
const router = useRouter()
const d = ref(null)
const meetingName = ref(null)
const meeting = ref(null)
const listOpen = ref(false)
const list = ref([])
const revelationsLabel = computed(() => (d.value.revelations.length < d.value.revelations_shown ? `${d.value.revelations.length} left` : d.value.revelations.length))
const footerLine = computed(() => d.value ? `${d.value.revelations.length} revelation${d.value.revelations.length === 1 ? '' : 's'} · nothing blocks you from going on` : '')

async function load() {
  d.value = await r.read('library')
  if (listOpen.value || !list.value.length) list.value = (await r.read('meetings_list')).rows
}
async function openMeeting(name) {
  if (!name) return
  meetingName.value = name
  meeting.value = null
  meeting.value = await r.read('meeting', { event: name })
}
function closeMeeting() { meetingName.value = null; meeting.value = null; load() }
async function refreshMeeting() {
  if (meetingName.value) meeting.value = await r.read('meeting', { event: meetingName.value })
  load()
}
async function meetingAct(method, args) { await r.act(method, args); refreshMeeting() }
async function act(f, index) {
  const a = f.actions.find((x) => x.index === index)
  if (a?.kind === 'open_meetings') {
    if (a.events?.length) openMeeting(a.events[0])
    return
  }
  // looking is not acting: these open the record or the list, and the finding stays
  if (a?.kind === 'open_record' && a.ref) return openRef(a.ref)
  if ((a?.kind === 'open_list' || a?.kind === 'open_reset') && a.to) return router.push(a.to)
  await r.act('finding_act', { insight: f.name, index, goal: meeting.value?.goal || undefined }, a?.kind === 'make_task' ? 'Task made.' : undefined)
  refreshMeeting()
}
async function plan(args) { await r.act('meeting_plan', args, 'Task made, linked to this meeting.'); refreshMeeting() }
async function doneMeeting(m) {
  await r.act('meeting_done', { event: m.name })
  if (m.next) openMeeting(m.next)
  else closeMeeting()
}
watch(() => r.head?.name, load)
onMounted(load)
async function dropPin(p) {
  await unpin(p.doctype, p.name)
  d.value.unused_pins = d.value.unused_pins.filter((x) => x.name !== p.name)
}
</script>
