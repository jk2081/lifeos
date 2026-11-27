<template>
  <template v-if="doc">
    <template v-if="on('details')">
    <Alert v-if="doc.badge" :theme="doc.badge.state === 'expired' ? 'red' : 'amber'"
      :title="`${doc.badge.state === 'expired' ? `Expired ${-doc.badge.days} days ago.` : doc.badge.days === 0 ? 'Expires today.' : `Expires in ${doc.badge.days} days.`} Time to renew.`" />
    <LifeFormLayout doctype="Life Vault Document" :values="form" :rows="[['title'], ['doc_type', 'holder', 'number_last4']]" :overrides="OVERRIDES" :titles="titles" :disabled="!writable" />
    <div v-if="writable"><Button variant="ghost" size="sm" icon-left="lucide-plus" label="Add a person as holder" @click="addPerson" /></div>
    <LifeFormLayout doctype="Life Vault Document" :values="form" :rows="[['issue_date', 'expiry_date', 'remind_days_before']]" :overrides="OVERRIDES" :disabled="!writable" />
    <AreaPicker label="Area" :model-value="form.area || ''" :disabled="!writable" @update:model-value="(v) => (form.area = v || null)" />
    <FormControl v-model="form.notes_md" type="textarea" label="Notes" :rows="3" :disabled="!writable" />
    <div v-if="writable" class="flex flex-wrap items-center gap-2"><Button variant="solid" :label="doc.name ? 'Save' : 'Add document'" @click="save" />
      <Button v-if="doc.name" label="Archive" @click="archive" /></div>
    <Backlinks v-if="doc.name" doctype="Life Vault Document" :name="doc.name" />
    </template>
    <section v-if="doc.name && on('file')">
      <template v-if="doc.file">
        <img v-if="fileKind(doc.file_name) === 'image'" :src="doc.file" :alt="doc.title" class="block w-full rounded-5 border border-outline-gray-1" />
        <object v-else-if="fileKind(doc.file_name) === 'pdf'" :data="doc.file" type="application/pdf" class="block h-[420px] w-full rounded-5 border border-outline-gray-1">
          <a class="text-ink-blue-8 hover:underline" :href="doc.file" target="_blank" rel="noopener">Open the file</a></object>
        <div class="mt-1.5 text-sm text-ink-gray-6"><a class="text-ink-blue-8 hover:underline" :href="doc.file" target="_blank" rel="noopener">{{ doc.file_name }}</a> {{ fileSize(doc.file_size) }}</div>
      </template>
      <div v-else class="text-sm text-ink-gray-6">No file yet.</div>
      <div v-if="writable" class="mt-2"><FileAttach doctype="Life Vault Document" :docname="doc.name" fieldname="file" :label="doc.file ? 'Replace file' : 'Attach a file'" @uploaded="attached" /></div>
    </section>
  </template>
</template>
<script setup>
// A vault document in the pane. The name "new" is the form for adding one.
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Alert, Button, FormControl, dialog, toast } from 'frappe-ui'
import LifeFormLayout from '@/framework/LifeFormLayout.vue'
import AreaPicker from '@/components/ui/AreaPicker.vue'
import FileAttach from '@/components/FileAttach.vue'
import Backlinks from '@/components/Backlinks.vue'
import { errorText, tryCall } from '@/lib/api'
import { itemData } from '@/data/item'
import { store } from '@/lib/store'
import { fileKind, fileSize } from '@/lib/upload'
import { loadLookups, lookups } from '@/lib/lookups'
import { openRef } from '@/lib/pane'
import { useRecord } from '@/lib/record'

const FIELDS = ['title', 'doc_type', 'holder', 'number_last4', 'issue_date', 'expiry_date', 'remind_days_before', 'area', 'notes_md']
const props = defineProps({ name: String, type: String, tab: String })
// the pane's tabs: Details, File. The form for a new document has no tabs.
const on = (t) => !props.tab || props.tab === t
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const doc = ref(null)
const form = reactive({})
const people = ref([])
// The fields come from the DocType's meta (LifeFormLayout); these are the words this screen uses for them.
const OVERRIDES = computed(() => ({
  doc_type: { label: 'Type' },
  holder: { filters: { space: doc.value?.space || store.space } },
  number_last4: { label: 'Number, last 4 only', props: { maxlength: 4 } },
  issue_date: { label: 'Issued' }, expiry_date: { label: 'Expires' }, remind_days_before: { label: 'Remind, days before' },
}))
// the holder's name, shown before the person search has loaded
const titles = computed(() => Object.fromEntries([...people.value.map((p) => ['Life Person::' + p.name, p.full_name]),
  ...(doc.value?.holder && doc.value.holder_name ? [['Life Person::' + doc.value.holder, doc.value.holder_name]] : [])]))
const canRestore = computed(() => store.spaces.find((s) => s.name === (doc.value?.space || store.space))?.access === 'Write')
const writable = computed(() => canRestore.value && !doc.value?.is_archived)

let snapshot = '{}'
function fill(d) {
  doc.value = d
  for (const f of FIELDS) form[f] = d[f] ?? null
  snapshot = JSON.stringify(form)
  emit('meta', d.name
    ? { title: d.title || 'Document', area: d.area, area_name: d.area_name, goal: d.goal, goal_title: d.goal_title,
      sub: [d.doc_type, d.holder_name].filter(Boolean).join(' · '), archived: !!d.is_archived, canRestore: canRestore.value,
      tabs: [{ value: 'details', label: 'Details' }, { value: 'file', label: 'File' }] }
    : { title: 'Add document', sub: 'Only the last four characters of a number are stored.' })
}
// The record comes from the data layer (in memory only: a vault document is never kept on the device) and follows the server.
// The server adds only what a record does not hold: the holder's and area's names, the expiry badge and the file's name and size.
function show(d, extra) {
  const merged = { ...extra, ...d, also_in: (d.also_in || []).map((r) => r.area), notes_md: d.notes_md || '' }
  if (JSON.stringify(form) !== snapshot) { doc.value = { ...merged }; return } // the person is typing: their edits stay
  fill(merged)
}
const { rec, save: saveRecord, loadExtra, draw } = useRecord('Life Vault Document', () => (props.name === 'new' ? '' : props.name), {
  fetchExtra: () => itemData.vault.get({ document: props.name }), show, onMissing: () => emit('missing'),
})
async function save() {
  try {
    const isNew = !doc.value.name
    if (isNew) {
      const d = await itemData.vault.save({ space: store.space, values: { ...form } })
      toast.success('Saved.')
      emit('changed')
      openRef('vault:' + d.name)
      return
    }
    await saveRecord(Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === '' ? null : v])))
    snapshot = JSON.stringify(form)
    toast.success('Saved.')
    emit('changed')
    loadExtra()
  } catch (e) {
    toast.error(errorText(e))
  }
}
// the file is already on the server, private and attached to this document: point the document's field at it
async function attached(f) {
  try {
    await itemData.vault.set_file({ document: doc.value.name, file_url: f.file_url })
    rec.reload()
    loadExtra()
    toast.success('File attached.')
    emit('changed')
  } catch (err) {
    toast.error(errorText(err))
  }
}
function addPerson() {
  dialog.prompt({
    title: 'Add a person as holder', confirmLabel: 'Add',
    fields: [{ name: 'full_name', label: 'Name of the person', required: true, validate: (v) => (String(v || '').trim() ? null : 'A name is needed.') }],
    // an error from the server shows in the dialog, which stays open
    onConfirm: async ({ values }) => {
      const p = await itemData.vault.add_person({ space: store.space, full_name: values.full_name.trim() })
      people.value.push(p)
      form.holder = p.name
      loadLookups(true)
    },
  })
}
async function archive() {
  if (await tryCall(() => itemData.archive.set({ doctype: 'Life Vault Document', name: doc.value.name, archived: 1 }), 'Archived.')) {
    emit('changed')
    emit('close')
  }
}
onMounted(async () => {
  await loadLookups()
  people.value = [...(lookups.people || [])]
  if (props.name === 'new') return fill({ doc_type: 'Other', remind_days_before: 60 })
  draw() // from the cache, before any request finishes
  loadExtra()
})
</script>
