<template>
  <PageHead title="Brain" sub="Reads everything that comes in and sorts it onto your goals. Here it shows its work and asks for your call." />
  <div class="page-body flex max-w-6xl flex-col gap-4" data-needs-you :data-total="data?.total ?? 0">
    <OldItems v-if="writable" @changed="load" />
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Stat label="Came in since yesterday" :value="data?.came_in.count ?? 0" data-stat-came-in :data-n="data?.came_in.count ?? 0">
        <template #sub>from {{ plural(data?.came_in.sources ?? 0, 'source') }}</template>
      </Stat>
      <Stat label="Filed on its own" :value="data?.filed.count ?? 0" data-stat-filed :data-n="data?.filed.count ?? 0">
        <template #sub>under {{ plural(data?.filed.areas ?? 0, 'area') }} and {{ plural(data?.filed.goals ?? 0, 'goal') }} ·
          <RouterLink class="text-ink-blue-8 hover:underline" to="/brain/activity" data-see-activity>see in Activity</RouterLink></template>
      </Stat>
      <Stat label="Needs you" :value="data?.total ?? 0" class="!border-outline-gray-8" data-stat-needs :data-n="data?.total ?? 0">
        <template #sub>{{ data?.total ? `about ${plural(Math.max(1, Math.ceil(data.total * 20 / 60 - 0.01)), 'minute')}` : 'nothing to decide' }}</template>
      </Stat>
    </div>

    <Card v-if="loaded && !rows.length && !unfiled.length && !lessons.length && !contradictions.length" class="py-2" data-needs-empty>
      <Empty title="Nothing needs you.">
        <p class="mt-1">Things you capture or connect will show up here.</p>
        <Button v-if="writable" class="mt-3" variant="solid" icon-left="lucide-plus" label="Capture" data-needs-capture @click="store.captureOpen = true" />
      </Empty>
    </Card>

    <Card v-if="asked.length" flush data-needs-rows>
      <div v-for="r in asked" :key="r.proposal" class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-b border-outline-gray-1 py-3 last:border-b-0"
        data-needs-row :data-proposal="r.proposal" :data-item="r.item" :data-kind="r.kind">
        <div class="min-w-0 flex-[1_1_320px]">
          <div class="flex flex-wrap items-center gap-2">
            <Badge theme="gray" :label="r.source" data-row-source />
            <span class="break-words text-base-medium text-ink-gray-9" data-row-title>{{ r.title }}</span>
          </div>
          <div v-if="r.reason" class="mt-0.5 text-sm text-ink-gray-6" data-row-reason><span aria-hidden="true">✦</span> {{ r.reason }}</div>
          <div v-if="r.blocked" class="mt-0.5 text-sm text-ink-amber-3" data-row-blocked>Needs a “Done when” before it can be kept. Use Change to add one.</div>
        </div>
        <div class="flex flex-wrap items-center gap-x-3 gap-y-2 max-md:w-full">
          <div class="flex flex-wrap items-center gap-1.5 text-sm text-ink-gray-6" data-best-guess>
            <span>Best guess:</span>
            <Badge :theme="r.kind === 'Task' ? 'blue' : 'gray'" :label="r.kind_label" data-row-kind />
            <template v-if="r.alt_area">
              <span class="inline-flex items-center gap-1.5 text-base text-ink-gray-9" data-area-chip="first"><span class="size-2 rounded-full" :class="dot(r.area)" aria-hidden="true" />{{ r.area_name }}</span>
              <span>or</span>
              <span class="inline-flex items-center gap-1.5 text-base text-ink-gray-9" data-area-chip="second"><span class="size-2 rounded-full" :class="dot(r.alt_area)" aria-hidden="true" />{{ r.alt_area_name }}</span>
            </template>
            <span v-else-if="r.area" class="inline-flex items-center gap-1.5 text-base text-ink-gray-9" data-area-chip="first"><span class="size-2 rounded-full" :class="dot(r.area)" aria-hidden="true" />{{ r.area_name }}</span>
            <span v-else-if="r.takes_area" class="text-ink-gray-6">no area yet</span>
          </div>
          <div v-if="writable" class="flex flex-wrap items-center gap-2" data-row-actions>
            <template v-if="r.alt_area">
              <Button :disabled="busy.has(r.proposal)" :label="r.area_name" :aria-label="`File in ${r.area_name}`" data-pick="first" @click="decide(r, 'accept', r.area)" />
              <Button :disabled="busy.has(r.proposal)" :label="r.alt_area_name" :aria-label="`File in ${r.alt_area_name}`" data-pick="second" @click="decide(r, 'accept', r.alt_area)" />
            </template>
            <template v-else>
              <Button variant="solid" label="Keep" :disabled="busy.has(r.proposal) || !!r.blocked" data-keep @click="decide(r, 'accept')" />
              <Button label="Change" :disabled="busy.has(r.proposal)" data-change @click="change(r)" />
            </template>
            <Button label="Drop" :disabled="busy.has(r.proposal)" data-drop @click="decide(r, 'reject')" />
          </div>
        </div>
      </div>
    </Card>

    <section v-if="contradictions.length" class="flex flex-col gap-2" data-needs-contradictions>
      <div>
        <h2 class="text-base-medium text-ink-gray-9">Pages disagree</h2>
        <p class="text-sm text-ink-gray-6">The weekly check found two facts that cannot both be true. Keep one and the pages follow it.</p>
      </div>
      <Card flush>
        <ContradictionCard v-for="c in contradictions" :key="c.name" :finding="c" :can-edit="writable" @changed="load" />
      </Card>
    </section>

    <section v-if="lessons.length" class="flex flex-col gap-2" data-needs-lessons>
      <div>
        <h2 class="text-base-medium text-ink-gray-9">Lessons</h2>
        <p class="text-sm text-ink-gray-6">Your corrections taught a skill something. Accept it and the skill follows it from now on.</p>
      </div>
      <Card flush>
        <LessonCard v-for="l in lessons" :key="l.name" :lesson="l" :can-edit="writable" @changed="load" />
      </Card>
    </section>

    <section v-if="unfiled.length || data?.unfiled?.length" class="flex flex-col gap-2" data-unfiled>
      <div>
        <h2 class="text-base-medium text-ink-gray-9">Unfiled</h2>
        <p class="text-sm text-ink-gray-6">The Brain could not place these. They stay here until you do.</p>
      </div>
      <Card flush>
        <div v-for="r in unfiled" :key="r.proposal" class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-b border-outline-gray-1 py-3 last:border-b-0"
          data-needs-row data-unfiled-row :data-proposal="r.proposal" :data-item="r.item">
          <div class="min-w-0 flex-[1_1_320px]">
            <div class="flex flex-wrap items-center gap-2"><Badge theme="gray" :label="r.source" /><span class="break-words text-base-medium text-ink-gray-9">{{ r.title }}</span></div>
            <div class="mt-0.5 text-sm text-ink-gray-6"><span aria-hidden="true">✦</span> {{ r.reason || 'No area fits yet.' }}</div>
          </div>
          <div class="flex flex-wrap items-center gap-2 max-md:w-full">
            <Badge :theme="r.kind === 'Task' ? 'blue' : 'gray'" :label="r.kind_label" />
            <Pick v-if="writable" :model-value="null" :options="areaOptions()" placeholder="Choose an area" :clearable="false" data-unfiled-area
              @update:model-value="(v) => v && decide(r, 'accept', v)" />
            <Button v-if="writable" label="Change" @click="change(r)" />
            <Button v-if="writable" label="Drop" :disabled="busy.has(r.proposal)" data-drop @click="decide(r, 'reject')" />
          </div>
        </div>
        <div v-for="u in data?.unfiled || []" :key="u.item" class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-b border-outline-gray-1 py-3 last:border-b-0"
          data-needs-row data-failed-row :data-item="u.item">
          <div class="min-w-0 flex-[1_1_320px]">
            <div class="flex flex-wrap items-center gap-2"><Badge theme="gray" :label="u.source" /><span class="break-words text-base-medium text-ink-gray-9">{{ u.title }}</span></div>
            <div class="mt-0.5 text-sm text-ink-gray-6"><span aria-hidden="true">✦</span> {{ u.reason || 'Could not be read.' }}</div>
          </div>
          <div class="flex flex-wrap items-center gap-2 max-md:w-full">
            <Button v-if="writable" label="Retry" data-retry @click="retry(u)" />
            <Button label="Open" @click="router.push(`/item/${u.item}`)" />
          </div>
        </div>
      </Card>
    </section>

    <div v-if="rows.length || data?.waiting" class="flex flex-wrap items-center justify-between gap-3 pt-1" data-needs-foot>
      <div class="text-sm text-ink-gray-6">
        <span v-if="rows.length">Every choice teaches the Brain. Next time it files these on its own.</span>
        <RouterLink v-if="data?.waiting" class="ml-1 text-ink-blue-8 hover:underline" :to="{ path: '/brain/queue', query: { status: 'Waiting' } }" data-waiting-link>
          {{ plural(data.waiting, 'capture') }} still with the agent</RouterLink>
      </div>
      <Button v-if="writable && filable.length" variant="solid" :loading="allBusy" :label="`Done, file all ${filable.length}`" data-file-all @click="fileAll" />
    </div>
  </div>
</template>
<script setup>
// Brain > Needs you (issue 17): what the Brain asks you to decide, at most seven at a time, each with its best guess and
// the reason. Keep accepts the guess, Change opens the capture's page, Drop rejects (the Outbox keeps it as Discarded). A
// proposal the Brain is torn on shows two area chips and you pick one. All of it is review.decide and review.decide_all.
// Lessons (issue 30): what your corrections taught a skill, to Accept, Edit or Reject.
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Pick from '@/components/Pick.vue'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import Stat from '@/components/ui/Stat.vue'
import OldItems from '@/components/inbox/OldItems.vue'
import LessonCard from '@/components/brain/LessonCard.vue'
import ContradictionCard from '@/components/brain/ContradictionCard.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { areaOptions, loadLookups, lookups } from '@/lib/lookups'
import { dotClass } from '@/lib/lens'

const router = useRouter()
const data = ref(null)
const loaded = ref(false)
const busy = reactive(new Set())
const allBusy = ref(false)
const writable = computed(() => canWrite() && !store.isAgent)
const rows = computed(() => data.value?.rows || [])
const lessons = computed(() => data.value?.lessons || [])
const contradictions = computed(() => data.value?.contradictions || [])
// a proposal that takes an area and has none cannot be kept as it is: it sits under Unfiled until you choose one
const unfiled = computed(() => rows.value.filter((r) => r.unfiled))
const asked = computed(() => rows.value.filter((r) => !r.unfiled))
const filable = computed(() => asked.value.filter((r) => !r.alt_area && !r.blocked))
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
const dot = (area) => dotClass((lookups.areas || []).find((a) => a.name === area))

async function load() {
  const res = await tryCall(() => api('brain.needs_you', { space: store.space }))
  if (res) data.value = res
  loaded.value = true
}
// Keep, Drop and a picked area chip are one decision on one proposal. `area` replaces the proposal's area (the chip picked).
async function decide(r, decision, area) {
  if (busy.has(r.proposal)) return
  busy.add(r.proposal)
  try {
    const payload = area ? { ...r.payload, area } : undefined
    await api('review.decide', { proposal: r.proposal, decision, payload })
    toast.success(decision === 'reject' ? `Dropped “${r.title}”.` : `Filed “${r.title}”${area ? ` under ${areaLabel(area)}` : ''}.`)
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.delete(r.proposal)
  }
  await load()
}
const areaLabel = (id) => (lookups.areas || []).find((a) => a.name === id)?.area_name || ''
function change(r) {
  router.push(`/item/${r.item}`)
}
// Done, file all: every row shown that has a best guess to keep. A capture whose pending proposals are all on screen goes
// through review.decide_all in one call; any other proposal is decided alone.
async function fileAll() {
  allBusy.value = true
  let done = 0, failed = 0
  try {
    const byItem = {}
    for (const r of filable.value) (byItem[r.item] ||= []).push(r)
    for (const [item, list] of Object.entries(byItem)) {
      const everyOne = list.length === list[0].item_pending
      try {
        if (everyOne) {
          const res = await api('review.decide_all', { item, decision: 'accept' })
          done += res.decided.length
          failed += res.errors.length
        } else {
          for (const r of list) {
            try { await api('review.decide', { proposal: r.proposal, decision: 'accept' }); done++ } catch { failed++ }
          }
        }
      } catch {
        failed += list.length
      }
    }
    if (failed) toast.error(`Filed ${done}. ${failed} could not be filed: open them with Change.`)
    else toast.success(`Filed ${done}.`)
  } finally {
    allBusy.value = false
  }
  await load()
}
async function retry(u) {
  if (await tryCall(() => api('inbox.retry', { item: u.item }), 'Sent back to the agent.')) await load()
}
onMounted(async () => { await loadLookups(); await load() })
watch(() => [store.space], load)
</script>
