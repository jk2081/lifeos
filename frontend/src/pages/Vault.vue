<template>
  <PageHead title="Vault" :sub="`${total} document${total === 1 ? '' : 's'} · ${expiring} expiring or expired`">
    <button v-if="canWrite()" class="bt p" type="button" @click="openNew">Add document</button>
  </PageHead>
  <div class="bd">
    <section v-for="g in groups" :key="g.holder">
      <h2 class="sh">{{ g.holder }}</h2>
      <div class="tblwrap"><div class="tblscroll"><table class="tbl">
        <thead><tr><th>Document</th><th>Type</th><th>Number</th><th>Expires</th><th>Area</th><th></th></tr></thead>
        <tbody><tr v-for="d in g.documents" :key="d.name" style="cursor: pointer" @click="open(d.name)">
          <td style="font-weight: 500; min-width: 180px">{{ d.title }}</td><td>{{ d.doc_type }}</td>
          <td style="font-variant-numeric: tabular-nums">{{ d.number_last4 ? '···· ' + d.number_last4 : '' }}</td>
          <td style="white-space: nowrap">{{ short(d.expiry_date, true) }}</td><td>{{ d.area_name }}</td>
          <td style="text-align: right"><span v-if="d.badge" class="pl" :class="d.badge.state === 'expired' ? 'r' : 'o'">{{ badgeText(d.badge) }}</span>
            <span v-else-if="d.file" class="pl n">File</span></td>
        </tr></tbody>
      </table></div></div>
    </section>
    <div v-if="loaded && !groups.length" class="cd"><Empty title="The vault is empty." hint="Keep IDs, travel papers, insurance and tax documents here with their expiry dates. Add one, or drop a scan in the Inbox." /></div>
    <p class="mt" style="margin: 0">Only the last four characters of any number are stored. Files are private to this space.</p>
  </div>

  <Panel v-if="doc" :title="doc.name ? doc.title || 'Document' : 'Add document'" :sub="doc.name && [doc.doc_type, doc.holder_name].filter(Boolean).join(' · ')" @close="close">
    <div v-if="doc.badge" class="cd" :style="`background: var(--${doc.badge.state === 'expired' ? 'r' : 'o'}-bg); color: var(--${doc.badge.state === 'expired' ? 'r' : 'o'}-ink); border-color: transparent`">
      {{ doc.badge.state === 'expired' ? `Expired ${-doc.badge.days} days ago.` : doc.badge.days === 0 ? 'Expires today.' : `Expires in ${doc.badge.days} days.` }} Time to renew.</div>
    <div class="field"><label class="lbl" for="v-title">Title</label><input id="v-title" v-model="form.title" class="inp" :disabled="!canWrite()" /></div>
    <div class="formgrid">
      <div class="field"><label class="lbl" for="v-type">Type</label><select id="v-type" v-model="form.doc_type" class="inp" :disabled="!canWrite()"><option v-for="t in TYPES" :key="t">{{ t }}</option></select></div>
      <div class="field"><label class="lbl" for="v-holder">Holder</label><select id="v-holder" v-model="form.holder" class="inp" :disabled="!canWrite()"><option :value="null">—</option>
        <option v-for="p in people" :key="p.name" :value="p.name">{{ p.full_name }}</option></select></div>
      <div class="field"><label class="lbl" for="v-last4">Number, last 4 only</label><input id="v-last4" v-model="form.number_last4" class="inp" maxlength="4" :disabled="!canWrite()" /></div>
    </div>
    <a v-if="canWrite()" href="#" class="mt" @click.prevent="addPerson">+ Add a person as holder</a>
    <div class="formgrid">
      <div class="field"><label class="lbl" for="v-issue">Issued</label><input id="v-issue" v-model="form.issue_date" type="date" class="inp" :disabled="!canWrite()" /></div>
      <div class="field"><label class="lbl" for="v-exp">Expires</label><input id="v-exp" v-model="form.expiry_date" type="date" class="inp" :disabled="!canWrite()" /></div>
      <div class="field"><label class="lbl" for="v-remind">Remind, days before</label><input id="v-remind" v-model.number="form.remind_days_before" type="number" min="0" class="inp" :disabled="!canWrite()" /></div>
    </div>
    <div class="field"><label class="lbl" for="v-area">Area</label><select id="v-area" v-model="form.area" class="inp" :disabled="!canWrite()"><option :value="null">—</option>
      <option v-for="o in areaOptions()" :key="o.value" :value="o.value">{{ o.label }}</option></select></div>
    <div class="field"><label class="lbl" for="v-notes">Notes</label><textarea id="v-notes" v-model="form.notes_md" class="inp" rows="3" :disabled="!canWrite()"></textarea></div>
    <div v-if="canWrite()" class="chips"><button class="bt p" type="button" @click="save">{{ doc.name ? 'Save' : 'Add document' }}</button>
      <button v-if="doc.name" class="bt s" type="button" @click="archive">Archive</button></div>
    <section v-if="doc.name">
      <h2 class="sh">File</h2>
      <template v-if="doc.file">
        <img v-if="fileKind(doc.file_name) === 'image'" :src="doc.file" :alt="doc.title" class="viewer" />
        <object v-else-if="fileKind(doc.file_name) === 'pdf'" :data="doc.file" type="application/pdf" class="viewer pdf"><a :href="doc.file" target="_blank" rel="noopener">Open the file</a></object>
        <div class="mt" style="margin-top: 6px"><a :href="doc.file" target="_blank" rel="noopener">{{ doc.file_name }}</a> {{ fileSize(doc.file_size) }}</div>
      </template>
      <div v-else class="mt">No file yet.</div>
      <label v-if="canWrite()" class="bt s" style="margin-top: 8px; cursor: pointer">{{ doc.file ? 'Replace file' : 'Attach a file' }}<input type="file" style="display: none" @change="upload" /></label>
    </section>
    <Backlinks v-if="doc.name" doctype="Life Vault Document" :name="doc.name" />
  </Panel>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import Panel from '@/components/Panel.vue'
import Backlinks from '@/components/Backlinks.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { fileKind, fileSize, uploadFile } from '@/lib/upload'
import { areaOptions, loadLookups } from '@/lib/lookups'

const TYPES = ['ID', 'Travel', 'Insurance', 'Property', 'Tax', 'Medical', 'Other']
const FIELDS = ['title', 'doc_type', 'holder', 'number_last4', 'issue_date', 'expiry_date', 'remind_days_before', 'area', 'notes_md']
const route = useRoute()
const router = useRouter()
const groups = ref([])
const people = ref([])
const total = ref(0)
const expiring = ref(0)
const loaded = ref(false)
const doc = ref(null)
const form = reactive({})
const badgeText = (b) => (b.state === 'expired' ? 'Expired' : b.days === 0 ? 'Expires today' : `Expires in ${b.days} days`)

async function load() {
  const res = await tryCall(() => api('vault.list', { space: store.space }))
  if (res) {
    groups.value = res.groups
    people.value = res.people
    total.value = res.total
    expiring.value = res.expiring
    loaded.value = true
  }
}
function fill(d) {
  doc.value = d
  for (const f of FIELDS) form[f] = d[f] ?? null
}
async function open(name) {
  const d = await tryCall(() => api('vault.get', { document: name }))
  if (d) fill(d)
}
function openNew() {
  fill({ doc_type: 'Other', remind_days_before: 60 })
}
function close() {
  doc.value = null
  if (route.query.open) router.replace({ query: {} })
}
async function save() {
  try {
    const d = await api('vault.save', { document: doc.value.name, space: store.space, values: { ...form } })
    toast.success('Saved.')
    fill(d)
    load()
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
    load()
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
  }
}
async function archive() {
  if (await tryCall(() => api('archive.set', { doctype: 'Life Vault Document', name: doc.value.name, archived: 1 }), 'Archived.')) {
    close()
    load()
  }
}
onMounted(() => {
  loadLookups()
  load()
  if (route.query.open) open(route.query.open)
})
</script>
<style scoped>
.viewer { width: 100%; border: 1px solid var(--line); border-radius: 10px; display: block; }
.viewer.pdf { height: 420px; }
</style>
