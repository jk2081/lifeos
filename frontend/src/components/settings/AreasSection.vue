<template>
  <!-- Settings > Your life > Areas (issue 12): the seven areas of life, each switched on or off, with their parts -->
  <div class="flex flex-col gap-4" data-areas-section>
    <p class="text-sm text-ink-gray-6">Seven areas cover a whole life. Switch on the ones you want the Brain to sort into. Add parts to an area for the things you run inside it.</p>
    <Card v-if="isAdmin || useFocuses" flush data-use-focuses-card>
      <div class="flex items-center gap-3 py-3">
        <Switch :model-value="useFocuses" :disabled="!isAdmin" aria-label="Use focuses" data-use-focuses @update:model-value="(v) => emit('use-focuses', v ? 1 : 0)" />
        <div class="min-w-0 flex-1">
          <div class="text-base font-medium text-ink-gray-9">Use focuses</div>
          <div class="text-sm text-ink-gray-6">A focus is ongoing work under a part, like Systems or Yield. It has a standard, principles and an annual goal. Off hides every focus; nothing is deleted.</div>
        </div>
      </div>
    </Card>
    <Card flush data-areas-card>
      <Row bare v-for="a in life" :key="a.name" class="py-3" :data-life-area="a.area_name" :data-on="a.is_on ? 1 : 0">
        <div class="flex items-center gap-3">
          <div class="flex flex-none items-center max-md:order-last">
            <Switch :model-value="!!a.is_on" :disabled="!isAdmin || busy === a.name" :aria-label="`${a.area_name} ${a.is_on ? 'on' : 'off'}`" :data-area-switch="a.area_name"
              @update:model-value="(v) => switchArea(a, v)" />
          </div>
          <span class="size-2.5 flex-none rounded-full" :class="[dotClass(a), !a.is_on && 'opacity-60']" aria-hidden="true" />
          <div class="min-w-0 flex-1" :class="!a.is_on && 'opacity-60'">
            <div class="text-base text-ink-gray-9"><span class="font-medium" data-area-name>{{ a.area_name }}</span>
              <span v-if="a.is_on && a.goals" class="ml-1 text-sm text-ink-gray-6" data-area-goals>{{ goalsText(a.goals) }}</span></div>
            <div class="text-sm text-ink-gray-6">{{ a.description }}</div>
            <Badge v-if="ON_BY_DEFAULT.includes(a.area_name)" class="mt-1 md:hidden" label="On by default" />
          </div>
          <Badge v-if="ON_BY_DEFAULT.includes(a.area_name)" class="max-md:hidden" label="On by default" data-on-by-default />
        </div>
        <div v-if="a.is_on && (partsOf(a).length || isAdmin)" class="flex flex-col gap-0.5 pb-1 pl-11 pt-2 max-md:pl-6" :data-parts-of="a.area_name">
          <template v-for="p in partsOf(a)" :key="p.name">
            <div class="flex min-h-7 items-center gap-2" :data-part="p.name" :data-part-name="p.area_name">
              <span class="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-0.5">
                <Badge size="md" :label="p.area_name" />
                <span class="text-sm text-ink-gray-6">{{ [p.part_kind, p.description, goalsText(p.goals) || 'no goals'].filter(Boolean).join(' · ') }}</span>
              </span>
              <Button v-if="isAdmin" size="sm" variant="ghost" class="!text-ink-blue-8" label="Edit" :aria-label="`Edit ${p.area_name}`" :data-edit-part="p.name" @click="edit(p)" />
            </div>
            <div v-if="useFocuses" class="flex flex-col gap-0.5 pl-6" :data-focuses-of="p.area_name">
              <FocusRow v-for="f in focusesOf(p)" :key="f.name" :f="f" :is-admin="isAdmin" :busy="busy === f.name" @switch="(v) => switchArea(f, v)" @edit="editFocus(f)" />
              <div v-if="isAdmin"><Button size="sm" variant="ghost" class="-ml-2 !text-ink-blue-8" icon-left="lucide-plus" :aria-label="`Add a focus to ${p.area_name}`" label="Add a focus" :data-add-focus="p.area_name" @click="addFocus(p)" /></div>
            </div>
          </template>
          <div v-if="useFocuses && (focusesOf(a).length)" class="flex flex-col gap-0.5" :data-focuses-of="a.area_name">
            <FocusRow v-for="f in focusesOf(a)" :key="f.name" :f="f" :is-admin="isAdmin" :busy="busy === f.name" @switch="(v) => switchArea(f, v)" @edit="editFocus(f)" />
          </div>
          <div v-if="isAdmin && useFocuses && !partsOf(a).length">
            <Button size="sm" variant="ghost" class="-ml-2 !text-ink-blue-8" icon-left="lucide-plus" :aria-label="`Add a focus to ${a.area_name}`" label="Add a focus" :data-add-focus="a.area_name" @click="addFocus(a)" />
          </div>
          <div v-if="isAdmin">
            <Button size="sm" variant="ghost" class="-ml-2 !text-ink-blue-8" icon-left="lucide-plus" :label="`Add a part of ${a.area_name}`" :data-add-part="a.area_name" @click="add(a)" />
          </div>
        </div>
      </Row>
    </Card>
    <p class="text-sm text-ink-gray-6" data-areas-footer>Switching an area off hides it and its goals; nothing is deleted. The Brain stops filing into it and sends those items to Needs you.</p>
    <p v-if="!isAdmin" class="text-sm text-ink-gray-6" data-areas-read-only>Only the owner can change areas.</p>
  </div>

  <!-- add or edit a part: name, a short description, colour; Archive from the edit form -->
  <Dialog v-model:open="formOpen" :title="form.name ? `Edit ${form.was}` : form.focus ? `Add a focus to ${form.parentTitle}` : `Add a part of ${form.parentTitle}`" size="sm"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: form.name ? 'Save' : 'Add', variant: 'solid', onClick: savePart }]">
    <div class="flex flex-col gap-3" data-part-form>
      <TextInput v-model="form.title" label="Name" :placeholder="form.focus ? 'For example Systems' : 'For example CIS Board'" data-part-title @keydown.enter="savePart" />
      <TextInput v-if="!form.focus" v-model="form.description" label="Short description" placeholder="For example Vice Chair" data-part-description @keydown.enter="savePart" />
      <Select v-if="!form.focus" v-model="form.kind" :options="KINDS" label="Kind of part" aria-label="Kind of part" data-part-kind @update:model-value="loadOffers" />
      <div v-if="!form.focus && useFocuses && offers.length" class="flex flex-col gap-2" data-focus-offers>
        <div class="text-sm text-ink-gray-6">Focuses for a {{ form.kind.toLowerCase() }}. Switch off the ones you do not want.</div>
        <div v-for="o in offers" :key="o.name" class="flex items-start gap-2" :data-focus-offer="o.name">
          <Switch v-model="o.on" :aria-label="o.name" />
          <div class="min-w-0"><div class="text-base text-ink-gray-9">{{ o.name }}</div><div class="text-sm text-ink-gray-6">{{ o.standard }}</div></div>
        </div>
      </div>
      <TextInput v-if="form.focus" v-model="form.standard" label="Standard" placeholder="What good looks like, in a line or two" data-focus-standard @keydown.enter="savePart" />
      <div v-if="!form.focus" class="flex items-center gap-2">
        <span class="size-2.5 rounded-full" :class="dotClass({ colour: form.colour })" aria-hidden="true" />
        <Select class="w-36" v-model="form.colour" :options="COLOURS" aria-label="Colour" data-part-colour />
      </div>
      <ErrorMessage v-if="formError" :message="formError" data-part-error />
      <div v-if="form.name" class="border-t border-outline-gray-1 pt-3">
        <Button theme="red" variant="subtle" icon-left="lucide-archive" :label="form.focus ? 'Archive this focus' : 'Archive this part'" data-archive-part @click="askArchive" />
      </div>
    </div>
  </Dialog>
  <Dialog v-model:open="archiveOpen" :title="`Archive ${archiving?.area_name || ''}?`" size="md"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Archive', variant: 'solid', onClick: archive }]">
    <div class="flex flex-col gap-3 text-base text-ink-gray-8" data-archive-part-dialog>
      <template v-if="work.goals || work.tasks">
        <p>{{ archiving?.area_name }} has {{ [work.goals && goalsText(work.goals, 'open goal'), work.tasks && goalsText(work.tasks, 'open task')].filter(Boolean).join(' and ') }}. Where should they go?</p>
        <Select v-model="moveTo" :options="targets" aria-label="Move them to" data-move-to />
      </template>
      <p>The part leaves this screen and the area pickers. Nothing is deleted: restore it from Archive and trash in Settings.</p>
      <ErrorMessage v-if="archiveError" :message="archiveError" />
    </div>
  </Dialog>
</template>
<script setup>
import Row from '@/components/ui/Row.vue'
import { settingsData } from '@/data/settings'
import { computed, reactive, ref } from 'vue'
import { Badge, Button, Dialog, ErrorMessage, Select, Switch, TextInput, toast } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import { dotClass } from '@/lib/lens'
import FocusRow from '@/components/settings/FocusRow.vue'
import { errorText } from '@/lib/api'

const props = defineProps({ space: { type: String, required: true }, rows: { type: Array, default: () => [] }, isAdmin: Boolean, useFocuses: Boolean })
const emit = defineEmits(['changed', 'use-focuses'])
const ON_BY_DEFAULT = ['Career', 'Health']
const COLOURS = ['blue', 'green', 'amber', 'red', 'violet', 'teal', 'orange', 'pink', 'cyan', 'gray'].map((c) => ({ label: c[0].toUpperCase() + c.slice(1), value: c }))

const live = computed(() => props.rows.filter((r) => !r.is_archived))
// the areas that are on first, each group in its own order, as in the mockup
const life = computed(() => live.value.filter((r) => r.is_life_area).sort((x, y) => (y.is_on || 0) - (x.is_on || 0) || (x.sort_order || 0) - (y.sort_order || 0)))
const partsOf = (a) => live.value.filter((r) => r.parent_area === a.name && !r.is_focus)
const focusesOf = (a) => live.value.filter((r) => r.parent_area === a.name && r.is_focus)
const goalsText = (n, noun = 'goal') => (n ? `${n} ${noun}${n === 1 ? '' : 's'}` : '')

const busy = ref('')
async function switchArea(a, on) {
  busy.value = a.name
  const was = a.is_on
  a.is_on = on ? 1 : 0
  try {
    await settingsData.settings.save_item({ kind: 'area', name: a.name, is_on: on ? 1 : 0 })
    toast.success(`${a.area_name} ${on ? 'on' : 'off'}`)
    emit('changed')
  } catch (e) {
    a.is_on = was
    toast.error(errorText(e))
  } finally {
    busy.value = ''
  }
}

const formOpen = ref(false)
const formError = ref('')
const KINDS = [{ label: 'No kind', value: '' }, ...['Company', 'Estate', 'Household', 'Other'].map((k) => ({ label: k, value: k }))]
const form = reactive({ name: '', was: '', parent: '', parentTitle: '', title: '', description: '', colour: 'gray', kind: '', focus: false, standard: '' })
const offers = ref([])
// the focuses a kind of part offers, each with its suggested standard, all on (issue 57)
async function loadOffers() {
  offers.value = form.kind && props.useFocuses && !form.name ? (await settingsData.settings.focus_offers({ kind: form.kind })).map((o) => ({ ...o, on: true })) : []
}
function add(a) {
  Object.assign(form, { name: '', was: '', parent: a.name, parentTitle: a.area_name, title: '', description: '', colour: a.colour || 'gray', kind: '', focus: false, standard: '' })
  offers.value = []
  formError.value = ''
  formOpen.value = true
}
function addFocus(parent) {
  Object.assign(form, { name: '', was: '', parent: parent.name, parentTitle: parent.area_name, title: '', description: '', colour: parent.colour || 'gray', kind: '', focus: true, standard: '' })
  formError.value = ''
  formOpen.value = true
}
function edit(p) {
  Object.assign(form, { name: p.name, was: p.area_name, parent: p.parent_area, parentTitle: '', title: p.area_name, description: p.description || '', colour: p.colour || 'gray', kind: p.part_kind || '', focus: false, standard: '' })
  offers.value = []
  formError.value = ''
  formOpen.value = true
  loadOffers()
}
function editFocus(f) {
  Object.assign(form, { name: f.name, was: f.area_name, parent: f.parent_area, parentTitle: '', title: f.area_name, description: '', colour: 'gray', kind: '', focus: true, standard: f.standard || '' })
  formError.value = ''
  formOpen.value = true
}
async function savePart() {
  if (!form.title.trim()) return (formError.value = 'A name is needed.')
  const values = form.focus ? { kind: 'area', title: form.title, standard: form.standard } : { kind: 'area', title: form.title, description: form.description, colour: form.colour, part_kind: form.kind }
  if (!form.focus && offers.value.length) values.focuses = offers.value.filter((o) => o.on).map((o) => o.name)
  try {
    if (form.name) await settingsData.settings.save_item({ ...values, name: form.name })
    else await settingsData.settings.save_item({ ...values, space: props.space, parent_area: form.parent, ...(form.focus ? { is_focus: 1 } : {}), sort_order: 100 + partsOf({ name: form.parent }).length })
    toast.success(form.name ? 'Saved' : 'Added')
    formOpen.value = false
    emit('changed')
  } catch (e) {
    formError.value = errorText(e)
  }
}

// archiving a part asks where its open goals and tasks go: its area of life or another of its parts
const archiveOpen = ref(false)
const archiveError = ref('')
const archiving = ref(null)
const work = reactive({ goals: 0, tasks: 0 })
const targets = ref([])
const moveTo = ref('')
async function askArchive() {
  const p = live.value.find((r) => r.name === form.name)
  try {
    const res = await settingsData.settings.area_open_work({ area: p.name })
    Object.assign(work, { goals: res.goals, tasks: res.tasks })
    targets.value = res.targets.map((t) => ({ label: t.is_life_area ? `${t.area_name} itself` : t.area_name, value: t.name }))
    moveTo.value = targets.value[0]?.value || ''
  } catch (e) {
    return (formError.value = errorText(e))
  }
  archiving.value = p
  archiveError.value = ''
  formOpen.value = false
  archiveOpen.value = true
}
async function archive() {
  const p = archiving.value
  try {
    await settingsData.settings.save_item({ kind: 'area', name: p.name, is_archived: 1, move_to: work.goals || work.tasks ? moveTo.value : undefined })
    const where = targets.value.find((t) => t.value === moveTo.value)?.label
    toast.success(work.goals || work.tasks ? `Archived; its open work moved to ${where}` : 'Archived')
    archiveOpen.value = false
    emit('changed')
  } catch (e) {
    archiveError.value = errorText(e)
  }
}
</script>
