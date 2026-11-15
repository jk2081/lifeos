<template>
  <template v-if="doc">
    <div v-if="doc.badge" class="cd" :style="`background: var(--${doc.badge.state === 'expired' ? 'r' : 'o'}-bg); color: var(--${doc.badge.state === 'expired' ? 'r' : 'o'}-ink); border-color: transparent`">
      {{ doc.badge.state === 'expired' ? `Expired ${-doc.badge.days} days ago.` : doc.badge.days === 0 ? 'Expires today.' : `Expires in ${doc.badge.days} days.` }} Time to renew.</div>
    <div class="field"><label class="lbl" for="v-title">Title</label><input id="v-title" v-model="form.title" class="inp" :disabled="!writable" /></div>
    <div class="formgrid">
      <div class="field"><label class="lbl" for="v-type">Type</label><select id="v-type" v-model="form.doc_type" class="inp" :disabled="!writable"><option v-for="t in VAULT_TYPES" :key="t">{{ t }}</option></select></div>
      <div class="field"><label class="lbl" for="v-holder">Holder</label><select id="v-holder" v-model="form.holder" class="inp" :disabled="!writable"><option :value="null">—</option>
        <option v-for="p in people" :key="p.name" :value="p.name">{{ p.full_name }}</option></select></div>
      <div class="field"><label class="lbl" for="v-last4">Number, last 4 only</label><input id="v-last4" v-model="form.number_last4" class="inp" maxlength="4" :disabled="!writable" /></div>
    </div>
    <a v-if="writable" href="#" class="mt" @click.prevent="addPerson">+ Add a person as holder</a>
    <div class="formgrid">
      <div class="field"><label class="lbl" for="v-issue">Issued</label><input id="v-issue" v-model="form.issue_date" type="date" class="inp" :disabled="!writable" /></div>
      <div class="field"><label class="lbl" for="v-exp">Expires</label><input id="v-exp" v-model="form.expiry_date" type="date" class="inp" :disabled="!writable" /></div>
      <div class="field"><label class="lbl" for="v-remind">Remind, days before</label><input id="v-remind" v-model.number="form.remind_days_before" type="number" min="0" class="inp" :disabled="!writable" /></div>
    </div>
    <div class="field"><label class="lbl" for="v-area">Area</label><select id="v-area" v-model="form.area" class="inp" :disabled="!writable"><option :value="null">—</option>
      <option v-for="o in areaOptions()" :key="o.value" :value="o.value">{{ o.label }}</option></select></div>
    <div class="field"><label class="lbl" for="v-notes">Notes</label><textarea id="v-notes" v-model="form.notes_md" class="inp" rows="3" :disabled="!writable"></textarea></div>
    <div v-if="writable" class="chips"><button class="bt p" type="button" @click="save">{{ doc.name ? 'Save' : 'Add document' }}</button>
      <button v-if="doc.name" class="bt s" type="button" @click="archive">Archive</button></div>
    <section v-if="doc.name">
      <h2 class="sh">File</h2>
      <template v-if="doc.file">
        <img v-if="fileKind(doc.file_name) === 'image'" :src="doc.file" :alt="doc.title" class="viewer" />
        <object v-else-if="fileKind(doc.file_name) === 'pdf'" :data="doc.file" type="application/pdf" class="viewer pdf"><a :href="doc.file" target="_blank" rel="noopener">Open the file</a></object>
        <div class="mt" style="margin-top: 6px"><a :href="doc.file" target="_blank" rel="noopener">{{ doc.file_name }}</a> {{ fileSize(doc.file_size) }}</div>
      </template>
      <div v-else class="mt">No file yet.</div>
      <label v-if="writable" class="bt s" style="margin-top: 8px; cursor: pointer">{{ doc.file ? 'Replace file' : 'Attach a file' }}<input type="file" style="display: none" @change="upload" /></label>
    </section>
    <Backlinks v-if="doc.name" doctype="Life Vault Document" :name="doc.name" />
  </template>
</template>
<script setup>
// A vault document in the pane. The name "new" is the form for adding one.
import { computed, onMounted, reactive, ref } from 'vue'
import { toast } from 'frappe-ui'
import Backlinks from '../Backlinks.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { fileKind, fileSize, uploadFile } from '@/lib/upload'
import { areaOptions, loadLookups, lookups } from '@/lib/lookups'
import { openRef } from '@/lib/pane'
import { VAULT_TYPES } from '@/lib/tasks'

const FIELDS = ['title', 'doc_type', 'holder', 'number_last4', 'issue_date', 'expiry_date', 'remind_days_before', 'area', 'notes_md']
const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const doc = ref(null)
const form = reactive({})
const people = ref([])
const canRestore = computed(() => store.spaces.find((s) => s.name === (doc.value?.space || store.space))?.access === 'Write')
const writable = computed(() => canRestore.value && !doc.value?.is_archived)

function fill(d) {
  doc.value = d
  for (const f of FIELDS) form[f] = d[f] ?? null
  emit('meta', d.name
    ? { title: d.title || 'Document', area: d.area, area_name: d.area_name, project: d.project, project_title: d.project_title,
      sub: [d.doc_type, d.holder_name].filter(Boolean).join(' · '), archived: !!d.is_archived, canRestore: canRestore.value }
    : { title: 'Add document', sub: 'Only the last four characters of a number are stored.' })
}
async function save() {
  try {
    const isNew = !doc.value.name
    const d = await api('vault.save', { document: doc.value.name, space: store.space, values: { ...form } })
    toast.success('Saved.')
    emit('changed')
    if (isNew) openRef('vault:' + d.name)
    else fill(d)
  } catch (e) {
    toast.error(errorText(e))
  }
}
async function upload(e) {
  const file = e.target.files[0]
  if (!file) return
  try {
    const f = await uploadFile(file, 'Life Vault Document', doc.value.name, 'file')
    fill(await api('vault.set_file', { document: doc.value.name, file_url: f.file_url }))
    toast.success('File attached.')
    emit('changed')
  } catch (err) {
    toast.error(errorText(err))
  }
}
async function addPerson() {
  const name = window.prompt('Name of the person')
  if (!name || !name.trim()) return
  const p = await tryCall(() => api('vault.add_person', { space: store.space, full_name: name.trim() }))
  if (p) {
    people.value.push(p)
    form.holder = p.name
    loadLookups(true)
  }
}
async function archive() {
  if (await tryCall(() => api('archive.set', { doctype: 'Life Vault Document', name: doc.value.name, archived: 1 }), 'Archived.')) {
    emit('changed')
    emit('close')
  }
}
onMounted(async () => {
  await loadLookups()
  people.value = [...(lookups.people || [])]
  if (props.name === 'new') return fill({ doc_type: 'Other', remind_days_before: 60 })
  try {
    fill(await api('vault.get', { document: props.name }))
  } catch (e) {
    emit('missing')
  }
})
</script>
<style scoped>
.viewer { width: 100%; border: 1px solid var(--outline-gray-1); border-radius: 10px; display: block; }
.viewer.pdf { height: 420px; }
</style>
