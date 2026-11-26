<template>
  <div class="flex flex-col gap-4" data-agent-panel :data-agent-name="a?.name">
    <template v-if="a">
      <Card v-if="a.changes.waiting || a.changes.failed" tint class="text-sm text-ink-gray-7" data-agent-sync>
        <template v-if="a.changes.waiting">{{ plural(a.changes.waiting, 'change') }} waiting for {{ a.name }} to pick up. They show here as applied once it confirms.</template>
        <template v-if="a.changes.failed"> {{ plural(a.changes.failed, 'change') }} failed. The reason is on the row.</template>
      </Card>

      <section class="flex flex-col gap-2" data-agent-section="waiting">
        <div><h2 class="text-base-medium text-ink-gray-9">Waiting for your OK</h2><p class="text-sm text-ink-gray-6">What {{ a.name }} wants to do and will not until you say so.</p></div>
        <AgentRequests v-if="a.waiting.length" :rows="a.waiting" @changed="load" />
        <Card v-else class="text-sm text-ink-gray-6" data-agent-empty="waiting">Nothing waits for you.</Card>
      </section>

      <section class="flex flex-col gap-2" data-agent-section="knows">
        <div><h2 class="text-base-medium text-ink-gray-9">What it knows</h2><p class="text-sm text-ink-gray-6">Facts {{ a.name }} keeps about you, and where each came from.</p></div>
        <Card v-if="a.facts.length" flush>
          <div v-for="f in a.facts" :key="f.name" class="flex flex-wrap items-start justify-between gap-x-3 gap-y-2 border-b border-outline-gray-1 py-3 last:border-b-0" data-fact :data-fact-id="f.id"
            :data-state="f.change ? f.change.status : ''">
            <div class="min-w-0 flex-[1_1_320px]">
              <form v-if="editing === f.name" class="flex gap-2" @submit.prevent="saveFact(f)">
                <TextInput v-model="draft" class="min-w-0 flex-1" aria-label="The fact" data-fact-input /><Button variant="solid" label="Save" type="submit" data-fact-save />
                <Button label="Cancel" @click="editing = null" />
              </form>
              <div v-else class="break-words text-base text-ink-gray-9" data-fact-text :class="f.change && f.change.kind === 'Fact delete' && 'line-through'">{{ f.text }}</div>
              <div class="mt-0.5 flex flex-wrap items-center gap-2 text-sm text-ink-gray-6">
                <span data-fact-origin>{{ [f.origin, f.learned_on].filter(Boolean).join(' · ') || 'Source not given' }}</span>
                <Badge v-if="f.stale" theme="orange" label="May be out of date" :title="f.stale_reason || ''" data-fact-stale />
                <ChangeBadge :change="f.change" />
              </div>
            </div>
            <div v-if="writable && editing !== f.name" class="flex items-center gap-2">
              <Button size="sm" label="Edit" data-fact-edit @click="startEdit(f)" />
              <Button size="sm" label="Delete" data-fact-delete @click="act(() => brainData.agentPage.delete_fact({ key, fact: f.name, space: store.space }))" />
            </div>
          </div>
        </Card>
        <Card v-else class="text-sm text-ink-gray-6" data-agent-empty="knows">Nothing yet. What {{ a.name }} learns about you will show up here once it is connected.</Card>
      </section>

      <section class="flex flex-col gap-2" data-agent-section="can">
        <div><h2 class="text-base-medium text-ink-gray-9">What it can do</h2><p class="text-sm text-ink-gray-6">On its own, asks you first, or off.</p></div>
        <Card flush>
          <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-outline-gray-1 py-3" data-owner-runs-now :data-on="a.owner_runs_now">
            <div><span class="text-base text-ink-gray-9">Your requests through this agent run at once</span><p class="text-sm text-ink-gray-6">Off, what you ask it waits in Needs you.</p></div>
            <Switch :model-value="!!a.owner_runs_now" :disabled="!writable" aria-label="Your requests through this agent run at once"
              @update:model-value="(v) => act(() => brainData.agentPage.set_owner_runs_now({ key, on: v ? 1 : 0, space: store.space }))" />
          </div>
          <div v-for="c in a.can" :key="c.key" class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-outline-gray-1 py-3 last:border-b-0" data-ability :data-ability-key="c.key" :data-mode="c.mode"
            :data-state="c.change ? c.change.status : ''">
            <div class="flex flex-wrap items-center gap-2"><span class="text-base text-ink-gray-9">{{ c.label }}</span><ChangeBadge :change="c.change" /></div>
            <Select v-if="!c.fixed" class="w-40" :model-value="c.mode" :options="MODES" :disabled="!writable" :aria-label="c.label" data-ability-select
              @update:model-value="(m) => act(() => brainData.agentPage.set_ability({ key, action: c.key, mode: m, space: store.space }))" />
            <span v-else class="text-sm text-ink-gray-6" data-ability-fixed>Always off</span>
          </div>
        </Card>
      </section>

      <section class="flex flex-col gap-2" data-agent-section="read">
        <div><h2 class="text-base-medium text-ink-gray-9">What it may read in Life OS</h2><p class="text-sm text-ink-gray-6">Life OS leaves out what is off, whatever {{ a.name }} asks for.</p></div>
        <Card flush>
          <label v-for="ar in a.areas" :key="ar.name" class="flex items-center justify-between gap-3 border-b border-outline-gray-1 py-3" data-area :data-area-id="ar.name" :data-on="ar.on">
            <span class="text-base text-ink-gray-9">{{ ar.title }}</span>
            <Switch :model-value="!!ar.on" :disabled="!writable" :label="ar.on ? 'On' : 'Off'" @update:model-value="(v) => act(() => brainData.agentPage.set_area({ key, area: ar.name, on: v ? 1 : 0, space: store.space }))" />
          </label>
          <div class="flex items-center justify-between gap-3 py-3" data-area-vault><span class="text-base text-ink-gray-9">The Vault</span><span class="text-sm text-ink-gray-6">Always off</span></div>
        </Card>
      </section>

      <section class="flex flex-col gap-2" data-agent-section="scheduled">
        <div><h2 class="text-base-medium text-ink-gray-9">Scheduled</h2><p class="text-sm text-ink-gray-6">{{ a.name }}'s jobs and when they run.</p></div>
        <Card v-if="a.jobs.length" flush>
          <div v-for="j in a.jobs" :key="j.name" class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-outline-gray-1 py-3 last:border-b-0" data-job :data-job-id="j.id" :data-paused="j.paused"
            :data-state="j.change ? j.change.status : ''">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2"><span class="break-words text-base text-ink-gray-9" data-job-title>{{ j.title }}</span><Badge v-if="j.paused" theme="gray" label="Paused" data-job-paused /><ChangeBadge :change="j.change" /></div>
              <div class="text-sm text-ink-gray-6">{{ [j.schedule, j.next_run && `next ${j.next_run}`].filter(Boolean).join(' · ') || 'No time given' }}</div>
              <div v-if="j.failed" class="text-sm text-ink-red-8" data-job-failed><span aria-hidden="true">✦</span> Failed{{ j.last_run ? ` ${j.last_run}` : '' }}: {{ j.last_error || 'no reason given' }}</div>
            </div>
            <Button v-if="writable" size="sm" :label="j.paused ? 'Resume' : 'Pause'" data-job-toggle @click="act(() => brainData.agentPage.pause_job({ key, job: j.name, paused: j.paused ? 0 : 1, space: store.space }))" />
          </div>
        </Card>
        <Card v-else class="text-sm text-ink-gray-6" data-agent-empty="scheduled">Nothing scheduled yet.</Card>
      </section>

      <section class="flex flex-col gap-2" data-agent-section="did">
        <div><h2 class="text-base-medium text-ink-gray-9">What it did</h2><p class="text-sm text-ink-gray-6">This week, {{ money(a.cost_week) }} in all.</p></div>
        <Card v-if="a.did.length" flush>
          <div v-for="d in a.did" :key="d.name" class="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-outline-gray-1 py-3 last:border-b-0" data-did :data-status="d.status">
            <div class="min-w-0"><span class="break-words text-base text-ink-gray-9" data-did-title>{{ d.title }}</span>
              <span class="ml-2 text-sm text-ink-gray-6">{{ d.status === 'Approved' ? 'Approved by you · ' : '' }}{{ d.when }}</span>
              <div v-if="d.asked_by" class="text-sm text-ink-gray-6" data-did-asked>{{ d.asked_by === 'owner' ? `Asked by you: “${d.request}”` : 'Its own idea, with your OK' }}{{ d.undone ? ' · undone' : '' }}</div>
              <div v-if="d.error" class="text-sm text-ink-red-8" data-did-error>Failed: {{ d.error }}</div></div>
            <div class="flex items-center gap-2"><Button v-if="d.can_undo && writable" size="sm" label="Undo" data-did-undo @click="undoDid(d)" />
              <span class="text-sm text-ink-gray-6">{{ money(d.cost) }}</span></div>
          </div>
        </Card>
        <Card v-else class="text-sm text-ink-gray-6" data-agent-empty="did">Nothing this week.</Card>
      </section>

      <section class="flex flex-col gap-2" data-agent-section="connector">
        <div><h2 class="text-base-medium text-ink-gray-9">The connector</h2><p class="text-sm text-ink-gray-6">A small skill and script your agent runs. It does not change the agent itself.</p></div>
        <Card class="flex flex-col gap-2 text-sm text-ink-gray-7">
          <p>{{ a.reported ? `Last heard from ${a.name} at ${a.reported}.` : `${a.name} has not reported yet.` }} It sends what it knows, can do and has scheduled when they change and once a day, and picks up your changes from here.</p>
          <p v-if="!a.reported" data-connector-how>Set it up with the README in <code>agent/connector/</code>, on the agent's server.</p>
          <div v-if="a.skills.length" data-agent-skills><div class="text-ink-gray-9">Skills it reported</div>
            <ul class="mt-1 list-disc pl-5"><li v-for="s in a.skills" :key="s.name">{{ s.name }}<span v-if="s.description" class="text-ink-gray-6"> · {{ s.description }}</span></li></ul></div>
          <form v-if="writable" class="flex flex-wrap items-end gap-2" @submit.prevent="rename"><FormControl v-model="nameDraft" label="Name" class="w-64" data-agent-rename-input />
            <Button label="Save name" type="submit" :disabled="nameDraft.trim() === (a.has_name ? a.name : '')" data-agent-rename /></form>
        </Card>
      </section>
    </template>
  </div>
</template>

<script setup>
// An agent's page (issue 85): what it waits for, knows, can do, may read, has scheduled and did, and the connector that carries the owner's changes to it.
// A change shows waiting until the connector confirms it, then applied, or failed with the reason.
import { computed, h, ref, watch } from 'vue'
import { Badge, Button, FormControl, Select, Switch, TextInput } from 'frappe-ui'
import AgentRequests from '@/components/brain/AgentRequests.vue'
import Card from '@/components/ui/Card.vue'
import { tryCall } from '@/lib/api'
import { brainData } from '@/data/brain'
import { store } from '@/lib/store'

const props = defineProps({ keyName: { type: String, required: true }, writable: Boolean })
const emit = defineEmits(['changed'])
const MODES = [{ label: 'On its own', value: 'auto' }, { label: 'Asks you', value: 'ask' }, { label: 'Off', value: 'off' }]
const key = computed(() => props.keyName)
const a = ref(null)
const editing = ref(null)
const draft = ref('')
const nameDraft = ref('')
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
async function undoDid(d) {
  if (await tryCall(() => brainData.agentPage.undo({ request: d.name, space: store.space }), 'Undone')) await load()
}
const money = (n) => `$${(n || 0).toFixed(2)}`

const ChangeBadge = (p) => (p.change ? h(Badge, { theme: p.change.status === 'failed' ? 'red' : p.change.status === 'waiting' ? 'orange' : 'green', 'data-change': p.change.status,
  label: p.change.status === 'failed' ? `Failed: ${p.change.reason || 'no reason given'}` : p.change.status === 'waiting' ? 'Waiting' : 'Applied' }) : null)
ChangeBadge.props = ['change']

function take(res) { if (res) { a.value = res; nameDraft.value = res.has_name ? res.name : '' } return res }
async function load() { take(await tryCall(() => brainData.agentPage.get({ key: key.value, space: store.space }))) }
async function act(fn) { take(await tryCall(fn)) }
function startEdit(f) { editing.value = f.name; draft.value = f.text }
async function saveFact(f) {
  if (draft.value.trim()) await act(() => brainData.agentPage.edit_fact({ key: key.value, fact: f.name, text: draft.value, space: store.space }))
  editing.value = null
}
const rename = async () => { await act(() => brainData.agentPage.rename({ key: key.value, name: nameDraft.value, space: store.space })); emit('changed') }
watch(key, load, { immediate: true })
watch(() => store.space, load)
defineExpose({ load })
</script>
