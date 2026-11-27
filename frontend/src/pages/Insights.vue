<template>
  <PageHead title="Insights" sub="Insights are written every morning at 06:00 and when you click Refresh">
    <Button v-if="canWrite()" label="Refresh insights" :loading="refreshing" data-insights-refresh @click="refresh" />
  </PageHead>
  <!-- Insights: status chips with counts, filters by kind and area, and how they are made -->
  <div class="page-body" data-insights>
    <div class="flex flex-wrap items-center gap-2">
      <TabButtons :model-value="istatus" :options="STATUS.map((s) => ({ label: `${s.label} ${ins?.tabs?.[s.value] ?? ''}`, value: s.value }))" data-insight-status
        @update:model-value="(v) => setQuery({ istatus: v === 'New' ? undefined : v })" />
      <span v-if="route.query.actionable" class="text-sm text-ink-gray-7">Needing a decision <Button size="sm" variant="ghost" icon="lucide-x" label="Show every kind" @click="setQuery({ actionable: undefined })" /></span>
      <div class="ml-auto flex gap-2">
        <Select class="w-40" :model-value="route.query.kind || ''" :options="[{ label: 'Kind: all', value: '' }, ...KINDS.map((k) => ({ label: k, value: k }))]" aria-label="Kind"
          @update:model-value="(v) => setQuery({ kind: v || undefined })" />
        <Select class="w-44" :model-value="route.query.area || ''" :options="[{ label: 'Area: all', value: '' }, ...areaOptions()]" aria-label="Area"
          @update:model-value="(v) => setQuery({ area: v || undefined })" />
      </div>
    </div>
    <Card flush class="!px-4">
      <div class="sr-only" data-lv-count>{{ ins?.total ?? 0 }}</div>
      <div v-for="r in ins?.rows || []" :key="r.name" class="border-b border-outline-gray-1 py-3 last:border-b-0" data-insight-row :data-insight="r.name" :data-kind="r.kind">
        <div class="flex flex-wrap items-center gap-3">
          <Badge class="w-32 justify-center" :theme="KIND_THEME[r.kind] || 'gray'" :label="r.kind" />
          <div class="min-w-0 flex-[1_1_18rem]"><div class="break-words text-base text-ink-gray-9">{{ r.title }}</div><div class="text-sm text-ink-gray-6">{{ r.based_on }}</div></div>
          <span class="w-40 text-sm text-ink-gray-6">{{ statusText(r) }}</span>
          <Button :label="openRow === r.name ? 'Close' : 'Open'" data-insight-open @click="openRow = openRow === r.name ? '' : r.name" />
        </div>
        <div v-if="openRow === r.name" class="mt-3 flex flex-col gap-3 pl-0 md:pl-36" data-insight-detail>
          <p v-if="r.body" class="text-base text-ink-gray-8">{{ r.body }}</p>
          <div class="flex flex-wrap gap-1.5 text-sm"><span class="text-ink-gray-6">Evidence:</span>
            <template v-for="(e, i) in r.evidence.slice(0, 12)" :key="e.name"><a v-if="e.ref" href="#" class="text-ink-blue-8 hover:underline" @click.prevent="openRef(e.ref)">{{ e.label || e.name }}</a>
              <span v-else class="text-ink-gray-7">{{ e.label || e.name }}</span><span v-if="i < Math.min(r.evidence.length, 12) - 1" class="text-ink-gray-6">·</span></template>
            <span v-if="r.evidence.length > 12" class="text-ink-gray-6">and {{ r.evidence.length - 12 }} more</span></div>
          <div v-if="canWrite()" class="flex flex-wrap gap-2">
            <template v-if="r.status === 'New'">
              <Button v-for="(a, i) in r.actions" :key="i" :variant="i === 0 ? 'solid' : 'subtle'" :label="a.label" :data-insight-action="a.kind" @click="act(r, i)" />
              <Dropdown :options="SNOOZE.map((s) => ({ label: s.label, onClick: () => snooze(r, s.days) }))"><Button label="Snooze" data-insight-snooze /></Dropdown>
              <Dropdown :options="[{ label: 'Dismiss', onClick: () => dismiss(r) }, ...REASONS.map((x) => ({ label: 'Dismiss: ' + x.toLowerCase(), onClick: () => dismiss(r, x) }))]">
                <Button variant="ghost" label="Dismiss" data-insight-dismiss /></Dropdown>
            </template>
            <Button v-else variant="subtle" label="Back to new" @click="restore(r)" />
          </div>
        </div>
      </div>
      <Empty v-if="ins && !ins.rows.length" :title="istatus === 'New' ? 'No new insights.' : 'Nothing here.'" hint="Insights are found every morning at 06:00, and when you click Refresh insights." />
    </Card>
    <Card class="bg-surface-gray-1" data-insights-how>
      <div class="text-base-medium text-ink-gray-9">How insights are made</div>
      <p class="mt-1 text-base text-ink-gray-7">Rules find the exact ones: tasks, open-ended goals and inbox items that have not moved, chat items people are waiting on, the 12 Week Year
        score, goals with no ticks or no tasks, habits and check-ins trending down, and Someday items due for review. When an API key is set, the AI also reads the last two weeks
        of chats, email digests, source summaries and notes for promises with no task, people waiting on you and recurring themes. Every insight links to the records behind it.
        Dismissing one tells the AI what you do not care about; the same insight is not shown again unless something changes. At most 12 new ones a day.</p>
      <p v-if="ins?.run_on" class="mt-1 text-sm text-ink-gray-6">Last run {{ ins.run_on }}.</p>
    </Card>
  </div>
</template>

<script setup>
import { brainData } from '@/data/brain'
// Insights (issue 120): what the Brain noticed. It was a tab of the Ask page; the chat moved to the panel on every screen and its History into the panel.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dropdown, Select, TabButtons, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import { db, errorText } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { areaOptions, loadLookups } from '@/lib/lookups'
import { openRef } from '@/lib/pane'

const route = useRoute()
const router = useRouter()
const ins = ref(null)
const refreshing = ref(false)
const openRow = ref(String(route.query.insight || ''))
const STATUS = [{ value: 'New', label: 'New' }, { value: 'Snoozed', label: 'Snoozed' }, { value: 'Acted', label: 'Acted on' }, { value: 'Dismissed', label: 'Dismissed' }]
const KINDS = ['Stuck', 'Waiting on you', 'Promise', '12 Week Year', 'Habit', 'Check-in', 'Theme', 'Someday']
const KIND_THEME = { Stuck: 'red', 'Waiting on you': 'amber', Promise: 'amber', '12 Week Year': 'blue', Habit: 'green', 'Check-in': 'green', Theme: 'violet', Someday: 'violet' }
const REASONS = ['Not relevant', 'Already done', 'Wrong']
const SNOOZE = [{ label: 'For 3 days', days: 3 }, { label: 'For a week', days: 7 }, { label: 'For a month', days: 30 }]
const istatus = computed(() => route.query.istatus || 'New')
const statusText = (r) => r.status === 'Snoozed' ? `Snoozed to ${short(r.snooze_until)}` : r.status === 'Acted' ? `Acted${r.acted_note ? ' · ' + r.acted_note : ''}`
  : r.status === 'Dismissed' ? `Dismissed${r.dismiss_reason ? ' · ' + r.dismiss_reason.toLowerCase() : ''}` : 'New'
const setQuery = (q) => router.replace({ query: { ...route.query, ...q } })

async function loadInsights() {
  try {
    ins.value = await brainData.insights.list({ space: store.space, status: istatus.value === 'all' ? 'all' : istatus.value, kind: route.query.kind, area: route.query.area,
      actionable: route.query.actionable ? 1 : undefined, page_length: 100 })
  } catch (e) { toast.error(errorText(e)) }
}
async function refresh() {
  refreshing.value = true
  try {
    const s = await brainData.insights.refresh({ space: store.space })
    toast.success(`${s.created} new insight${s.created === 1 ? '' : 's'}${s.ai ? '. ' + s.ai : ''}`)
    await loadInsights()
  } catch (e) { toast.error(errorText(e)) } finally { refreshing.value = false }
}
async function act(r, i) {
  const a = r.actions[i]
  if (a.kind === 'open_reset') return router.push('/settings?tab=data')
  if (a.kind === 'open_list') return router.push(a.to)
  if (a.kind === 'open_record') return openRef(a.ref)
  try {
    const out = await brainData.insights.act({ insight: r.name, index: i })
    toast.success(out.kind === 'make_task' ? 'Task made.' : `${a.label}: done.`, out.undo ? { duration: 60000, action: { label: 'Undo', onClick: async () => {
      await brainData.reset.undo({ log: JSON.stringify(out.undo) }); await db.set('Life Insight', r.name, { status: 'New' }); loadInsights() } } } : undefined)
    loadInsights()
  } catch (e) { toast.error(errorText(e)) }
}
async function snooze(r, days) {
  const until = new Date(Date.now() + days * 86400e3 + 5.5 * 3600e3).toISOString().slice(0, 10)
  await db.set('Life Insight', r.name, { status: 'Snoozed', snooze_until: until })
  toast.success(`Snoozed until ${short(until)}.`)
  loadInsights()
}
async function dismiss(r, reason) {
  await db.set('Life Insight', r.name, { status: 'Dismissed', dismiss_reason: reason || '' })
  toast.success('Dismissed.', { duration: 60000, action: { label: 'Undo', onClick: async () => { await db.set('Life Insight', r.name, { status: 'New' }); loadInsights() } } })
  loadInsights()
}
async function restore(r) { await db.set('Life Insight', r.name, { status: 'New' }); loadInsights() }
watch(() => [route.query.istatus, route.query.kind, route.query.area, route.query.actionable], loadInsights)
onMounted(async () => {
  loadLookups()
  loadInsights()
})
</script>
