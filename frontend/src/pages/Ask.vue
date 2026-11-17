<template>
  <PageHead title="Ask" :sub="sub">
    <span v-if="tab.current.value === 'ask' && st" class="text-sm text-ink-gray-7" data-ask-spend>{{ st.text }}</span>
    <Button v-if="tab.current.value === 'insights' && canWrite()" label="Refresh insights" :loading="refreshing" data-insights-refresh @click="refresh" />
  </PageHead>
  <TabBar inset :tabs="TABS_SHOWN" :model-value="tab.current.value" label="Ask sections" @update:model-value="tab.set" />

  <!-- Ask: a thread, with the records it used and questions to try -->
  <div v-show="tab.current.value === 'ask'" class="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(0,1fr)_22rem]" data-ask-page>
    <div class="flex min-h-[60vh] flex-col gap-4 px-4 pb-6 pt-4 md:px-7">
      <div class="flex-1"><AskThread />
        <div v-if="!ask.messages.length && !ask.refusal" class="text-base text-ink-gray-6" data-ask-empty>Ask about anything in your records. Answers cite where they came from and suggest
          what to do; nothing changes until you click.</div></div>
      <div class="sticky bottom-[calc(76px+env(safe-area-inset-bottom))] md:bottom-4"><AskComposer /></div>
    </div>
    <aside class="flex flex-col gap-5 border-outline-gray-1 px-4 py-4 md:border-l md:px-5">
      <section v-if="lastAnswer && lastAnswer.cited?.length" data-ask-used>
        <h2 class="mb-2 text-base-medium text-ink-gray-9">Records used for this answer</h2>
        <div v-for="c in lastAnswer.cited" :key="c.n" class="flex gap-2.5 border-b border-outline-gray-1 py-2.5 last:border-b-0">
          <Badge theme="blue" :label="String(c.n)" />
          <div class="min-w-0"><a href="#" class="break-words text-base text-ink-blue-8 hover:underline" @click.prevent="openCite(lastAnswer, c.n)">{{ c.title }}</a>
            <div class="text-sm text-ink-gray-6">{{ [c.kind, c.date && short(c.date)].filter(Boolean).join(' · ') }}</div></div>
        </div>
      </section>
      <p class="text-sm text-ink-gray-6">Ask reads only what you can see in {{ store.space }}<template v-if="st && !st.vault">, never the Vault</template>. It never changes anything until you click a suggested action.</p>
      <section v-if="st?.suggested">
        <h2 class="mb-1.5 text-base-medium text-ink-gray-9">Try asking</h2>
        <Button v-for="q in st.suggested" :key="q" variant="ghost" class="!h-auto w-full !justify-start !whitespace-normal py-1.5 text-left !font-normal !text-ink-gray-7" :label="q"
          data-ask-try @click="tryAsk(q)" />
      </section>
    </aside>
  </div>

  <!-- Insights: status chips with counts, filters by kind and area, and how they are made -->
  <div v-if="tab.shown('insights')" v-show="tab.current.value === 'insights'" class="page-body" data-insights>
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

  <!-- History: past threads, searchable, deletable -->
  <div v-if="tab.shown('history')" v-show="tab.current.value === 'history'" class="page-body" data-ask-history>
    <TextInput class="max-w-md" :model-value="hq" placeholder="Search your questions and answers" aria-label="Search history" @update:model-value="(v) => { hq = v; loadHistory() }" />
    <Card flush class="!px-4">
      <Row v-for="t in hist.rows" :key="t.name" class="!items-center" data-history-row>
        <div class="min-w-0 flex-1"><a href="#" class="break-words text-base text-ink-gray-9 hover:underline" @click.prevent="openThread(t.name)">{{ t.title }}</a>
          <div class="text-sm text-ink-gray-6">{{ [t.scope_label, t.questions + ' question' + (t.questions === 1 ? '' : 's'), t.last_message_on].filter(Boolean).join(' · ') }}</div></div>
        <Button variant="ghost" icon="lucide-trash-2" :label="'Delete ' + t.title" data-history-delete @click="remove(t)" />
      </Row>
      <Empty v-if="!hist.rows.length" title="No questions yet." hint="Questions you ask from any screen are kept here, for you only." />
    </Card>
  </div>
</template>

<script setup>
// The Ask page (UX fixes, set 5): Ask (a thread, the records it used, questions to try), Insights and History.
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dropdown, Select, TabButtons, TextInput, dialog, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import TabBar from '@/components/TabBar.vue'
import AskThread from '@/components/ask/AskThread.vue'
import AskComposer from '@/components/ask/AskComposer.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import Empty from '@/components/Empty.vue'
import { api, errorText } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { areaOptions, loadLookups } from '@/lib/lookups'
import { openRef } from '@/lib/pane'
import { useUrlTab } from '@/lib/tabs'
import { ask, loadThread, openCite, scopeFromRoute, send } from '@/lib/ask'

const route = useRoute()
const router = useRouter()
const st = ref(null)
const ins = ref(null)
const refreshing = ref(false)
const openRow = ref('')
const hq = ref('')
const hist = reactive({ rows: [], total: 0 })
const STATUS = [{ value: 'New', label: 'New' }, { value: 'Snoozed', label: 'Snoozed' }, { value: 'Acted', label: 'Acted on' }, { value: 'Dismissed', label: 'Dismissed' }]
const KINDS = ['Stuck', 'Waiting on you', 'Promise', '12 Week Year', 'Habit', 'Check-in', 'Theme', 'Someday']
const KIND_THEME = { Stuck: 'red', 'Waiting on you': 'amber', Promise: 'amber', '12 Week Year': 'blue', Habit: 'green', 'Check-in': 'green', Theme: 'violet', Someday: 'violet' }
const REASONS = ['Not relevant', 'Already done', 'Wrong']
const SNOOZE = [{ label: 'For 3 days', days: 3 }, { label: 'For a week', days: 7 }, { label: 'For a month', days: 30 }]
const TABS_SHOWN = computed(() => [{ value: 'ask', label: 'Ask' }, { value: 'insights', label: 'Insights', count: ins.value?.tabs?.New }, { value: 'history', label: 'History' }])
const tab = useUrlTab('tab', TABS_SHOWN)
const istatus = computed(() => route.query.istatus || 'New')
const lastAnswer = computed(() => [...ask.messages].reverse().find((m) => m.role === 'assistant'))
const sub = computed(() => tab.current.value === 'insights' ? 'Insights are written every morning at 06:00 and when you click Refresh'
  : `Answers come from your records in ${store.space}${st.value && !st.value.vault ? ' · Vault excluded' : ''}`)
const statusText = (r) => r.status === 'Snoozed' ? `Snoozed to ${short(r.snooze_until)}` : r.status === 'Acted' ? `Acted${r.acted_note ? ' · ' + r.acted_note : ''}`
  : r.status === 'Dismissed' ? `Dismissed${r.dismiss_reason ? ' · ' + r.dismiss_reason.toLowerCase() : ''}` : 'New'
const setQuery = (q) => router.replace({ query: { ...route.query, ...q } })

function tryAsk(q) {
  ask.thread = null
  ask.messages = []
  ask.scope = scopeFromRoute()
  send(q)
}
async function openThread(name) {
  await loadThread(name)
  tab.set('ask')
}
async function loadInsights() {
  try {
    ins.value = await api('insights.list', { space: store.space, status: istatus.value === 'all' ? 'all' : istatus.value, kind: route.query.kind, area: route.query.area,
      actionable: route.query.actionable ? 1 : undefined, page_length: 100 })
  } catch (e) { toast.error(errorText(e)) }
}
async function refresh() {
  refreshing.value = true
  try {
    const s = await api('insights.refresh', { space: store.space })
    toast.success(`${s.created} new insight${s.created === 1 ? '' : 's'}${s.ai ? '. ' + s.ai : ''}`)
    await loadInsights()
  } catch (e) { toast.error(errorText(e)) } finally { refreshing.value = false }
}
async function act(r, i) {
  const a = r.actions[i]
  if (a.kind === 'open_reset') return router.push('/reset')
  if (a.kind === 'open_list') return router.push(a.to)
  if (a.kind === 'open_record') return openRef(a.ref)
  try {
    const out = await api('insights.act', { insight: r.name, index: i })
    toast.success(out.kind === 'make_task' ? 'Task made.' : `${a.label}: done.`, out.undo ? { duration: 60000, action: { label: 'Undo', onClick: async () => {
      await api('reset.undo', { log: JSON.stringify(out.undo) }); await api('insights.restore', { insight: r.name }); loadInsights() } } } : undefined)
    loadInsights()
  } catch (e) { toast.error(errorText(e)) }
}
async function snooze(r, days) {
  const until = new Date(Date.now() + days * 86400e3 + 5.5 * 3600e3).toISOString().slice(0, 10)
  await api('insights.snooze', { insight: r.name, until })
  toast.success(`Snoozed until ${short(until)}.`)
  loadInsights()
}
async function dismiss(r, reason) {
  await api('insights.dismiss', { insight: r.name, reason })
  toast.success('Dismissed.', { duration: 60000, action: { label: 'Undo', onClick: async () => { await api('insights.restore', { insight: r.name }); loadInsights() } } })
  loadInsights()
}
async function restore(r) { await api('insights.restore', { insight: r.name }); loadInsights() }
async function loadHistory() {
  try { Object.assign(hist, await api('ask.threads', { space: store.space, q: hq.value || undefined })) } catch (e) { /* shown as empty */ }
}
function remove(t) {
  dialog.danger({ title: 'Delete this question?', message: `“${t.title}” and its answers are deleted for good.`, confirmLabel: 'Delete',
    onConfirm: async () => { await api('ask.delete_thread', { name: t.name }); if (ask.thread === t.name) { ask.thread = null; ask.messages = [] } loadHistory() } })
}
watch(() => [route.query.istatus, route.query.kind, route.query.area, route.query.actionable], loadInsights)
watch(() => tab.current.value, (v) => { if (v === 'history') loadHistory() })
watch(() => route.query.thread, (v) => { if (v) loadThread(String(v)) }, { immediate: true })
onMounted(async () => {
  loadLookups()
  if (!ask.scope) ask.scope = scopeFromRoute()
  try { st.value = await api('ask.status', { space: store.space }) } catch (e) { st.value = null }
  loadInsights()
  if (tab.current.value === 'history') loadHistory()
})
</script>
