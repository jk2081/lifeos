<template>
  <PageHead title="Brain" sub="The skills that run Life OS's own judgment. Each is plain words you can read and change.">
    <Button v-if="canEdit" variant="solid" icon-left="lucide-plus" label="New skill" data-new-skill @click="openNew" />
  </PageHead>
  <div class="page-body flex max-w-6xl flex-col gap-6" data-brain-skills :data-loaded="loaded ? 1 : 0">
    <div v-if="loaded && skills.length" class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      <Card v-for="s in skills" :key="s.name" class="relative flex flex-col gap-2 hover:bg-surface-gray-1" data-skill-card :data-skill="s.name" :data-active="s.active ? 1 : 0">
        <RouterLink :to="`/brain/skills/${s.name}`" class="absolute inset-0 rounded-5 focus-visible:focus-ring" :aria-label="`Open ${s.title}`" data-skill-open />
        <div class="flex items-start gap-3">
          <div class="min-w-0 flex-1">
            <div class="truncate text-base-medium text-ink-gray-9">{{ s.title }}</div>
            <div class="truncate text-sm text-ink-gray-6">{{ s.name }}</div>
          </div>
          <Switch class="relative" :model-value="s.active" :disabled="!canEdit" :label="s.active ? 'On' : 'Off'" data-skill-switch @update:model-value="(v) => toggle(s, v)" />
        </div>
        <p class="text-sm text-ink-gray-7">{{ s.when_to_use }}</p>
        <div class="flex flex-wrap items-center gap-1.5 text-sm text-ink-gray-6">
          <Badge theme="gray" :label="s.trigger" />
          <Badge theme="gray" :label="`v${s.version}`" data-skill-version />
          <Badge :theme="s.source === 'Built-in' ? 'blue' : 'green'" :label="s.edited ? `${s.source}, edited` : s.source" />
          <Badge v-if="s.update_available" theme="amber" label="Update available" data-skill-update />
        </div>
        <p class="text-sm text-ink-gray-6" data-skill-month>{{ s.runs }} run{{ s.runs === 1 ? '' : 's' }} this month · ${{ s.cost.toFixed(2) }}</p>
      </Card>
    </div>
    <Card v-else-if="loaded" data-skills-empty>
      <Empty title="No skills yet.">Skills you switch on or write will show up here.
        <Button v-if="canEdit" class="mt-3" variant="solid" icon-left="lucide-plus" label="New skill" @click="openNew" /></Empty>
    </Card>

    <section v-if="loaded && autoFile" class="flex flex-col gap-2" data-auto-file>
      <h2 class="text-base-medium text-ink-gray-9">Filing on its own</h2>
      <Card class="flex flex-col gap-3">
        <p class="text-sm text-ink-gray-6">The Brain files a proposal without asking only when it is at least this sure and its kind is ticked. Nothing is ticked until you tick it, so everything waits for you.</p>
        <div class="flex flex-wrap items-center gap-2"><span class="text-sm text-ink-gray-7">Sure enough at</span>
          <FormControl v-model="threshold" type="number" :min="0.5" :max="1" :step="0.05" class="w-24" :disabled="!canEdit" data-auto-threshold /></div>
        <div class="flex flex-wrap gap-x-4 gap-y-2">
          <Checkbox v-for="k in kinds" :key="k" :model-value="chosen.includes(k)" :label="k" :disabled="!canEdit" :data-auto-kind="k" @update:model-value="(v) => tick(k, v)" />
        </div>
        <div v-if="canEdit"><Button label="Save" data-auto-save @click="saveAuto" /></div>
      </Card>
    </section>
  </div>

  <Dialog v-model:open="newOpen" title="New skill" :actions="[{ label: 'Create', variant: 'solid', onClick: create }]">
    <template #default>
      <div class="flex flex-col gap-3" data-new-skill-form>
        <FormControl v-model="draft.title" label="Name" placeholder="For example Weekly thank-you notes" data-new-title />
        <FormControl v-model="draft.when_to_use" label="When to use" placeholder="One line" />
        <FormControl v-model="draft.trigger_kind" type="select" label="Starts from" :options="lists.triggers" />
        <FormControl v-if="draft.trigger_kind === 'Event'" v-model="draft.trigger_event" type="select" label="Event" :options="lists.events" />
        <FormControl v-if="draft.trigger_kind === 'Schedule'" v-model="draft.schedule_cron" label="Schedule" placeholder="0 7 * * *" />
        <div><div class="mb-1 text-sm text-ink-gray-7">Tools it may use</div>
          <div class="flex flex-wrap gap-x-4 gap-y-1"><Checkbox v-for="t in allTools" :key="t" :model-value="draft.tools.includes(t)" :label="t" @update:model-value="(v) => pickTool(t, v)" /></div></div>
        <FormControl v-model="draft.output_kind" type="select" label="Output" :options="lists.outputs" />
        <FormControl v-model="draft.model_tier" type="select" label="Model" :options="lists.tiers" />
        <FormControl v-model="draft.instructions" type="textarea" :rows="6" label="Instructions" placeholder="Say in plain words what it should do." />
        <p class="text-sm text-ink-gray-6">A new skill starts switched off. It can only use the tools listed here, and none of them accepts, deletes or sends anything.</p>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
// Brain > Skills (issue 28): one card for each skill, with when to use, its trigger, version, source, runs and cost this month, and on or
// off. A new skill is written here from the fixed lists of triggers, tools and outputs. What the Brain may file on its own is set below.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, Checkbox, Dialog, FormControl, Switch } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import PageHead from '@/components/PageHead.vue'
import { tryCall } from '@/lib/api'
import { brainData } from '@/data/brain'
import { store } from '@/lib/store'

const router = useRouter()
const skills = ref([])
const lists = ref({ triggers: [], events: [], outputs: [], tiers: [], tools: { read: [], write: [] } })
const kinds = ref([])
const autoFile = ref(null)
const chosen = ref([])
const threshold = ref(0.85)
const canEdit = ref(false)
const loaded = ref(false)
const newOpen = ref(false)
const blank = () => ({ title: '', when_to_use: '', trigger_kind: 'Button', trigger_event: 'Capture created', schedule_cron: '', tools: [], output_kind: 'Answer', model_tier: 'Fast', instructions: '' })
const draft = ref(blank())
const allTools = computed(() => [...lists.value.tools.read, ...lists.value.tools.write])

async function load() {
  const res = await tryCall(() => brainData.skills.overview())
  if (res) {
    skills.value = res.skills
    lists.value = res.lists
    kinds.value = res.proposal_kinds
    autoFile.value = res.auto_file
    chosen.value = [...res.auto_file.kinds]
    threshold.value = res.auto_file.threshold
    canEdit.value = res.can_edit
  }
  loaded.value = true
}
watch(() => store.space, load, { immediate: true })

async function toggle(s, on) {
  const res = await tryCall(() => brainData.skills.set_active({ name: s.name, active: on ? 1 : 0 }), on ? `${s.title} is on.` : `${s.title} is off.`)
  if (res) s.active = res.active
}
const tick = (k, v) => { chosen.value = v ? [...new Set([...chosen.value, k])] : chosen.value.filter((x) => x !== k) }
async function saveAuto() {
  const res = await tryCall(() => brainData.skills.save_auto_file({ threshold: Number(threshold.value), kinds: JSON.stringify(chosen.value) }), 'Saved.')
  if (res) { chosen.value = [...res.kinds]; threshold.value = res.threshold }
}
function openNew() { draft.value = blank(); newOpen.value = true }
const pickTool = (t, v) => { draft.value.tools = v ? [...draft.value.tools, t] : draft.value.tools.filter((x) => x !== t) }
async function create() {
  const d = draft.value
  if (!d.title.trim()) return
  const res = await tryCall(() => brainData.skills.create({ slug: d.title, values: JSON.stringify({ ...d, tools: d.tools }) }), 'Skill created. It is switched off until you turn it on.')
  if (res) { newOpen.value = false; router.push(`/brain/skills/${res.name}`) }
}
</script>
