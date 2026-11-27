<template>
  <PageHead :title="page?.header.title || 'Page'" :path="[{ label: 'Library', to: '/library' }, { label: 'Pages', to: '/library/pages' }]">
    <template v-if="page">
      <Button :variant="page.pinned ? 'subtle' : 'solid'" :icon-left="page.pinned ? 'lucide-pin-off' : 'lucide-pin'" :label="page.pinned ? 'Pinned' : 'Pin'" data-page-pin @click="togglePin" />
      <Dropdown v-if="canEdit" :options="menu" placement="right"><Button variant="ghost" icon="lucide-ellipsis" label="More" data-page-menu /></Dropdown>
    </template>
  </PageHead>
  <div class="page-body max-w-5xl" data-library-page :data-loaded="page ? 1 : 0" :data-kind="page?.header.kind" :data-doctype="doctype" :data-name="name">
    <Card v-if="missing" class="py-2" data-page-missing><EmptyState line="Not found. This page is gone, or is not in a space you can see." /></Card>
    <template v-else-if="page">
      <!-- the header -->
      <Card class="flex flex-wrap items-center gap-x-4 gap-y-2" data-page-header>
        <span :class="KIND_ICON[page.header.kind]" class="size-6 flex-none text-ink-gray-7" aria-hidden="true" data-page-icon />
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="break-words text-lg-semibold text-ink-gray-9" data-page-name>{{ page.header.title }}</h2>
            <Badge size="sm" :label="page.header.kind_label" data-page-kind />
            <FormControl v-if="page.header.kind === 'company' && canEdit" class="w-36" type="select" size="sm" :model-value="page.header.status || ''" :options="STATUS_OPTIONS" aria-label="Status"
              data-page-status-select @update:model-value="setStatus" />
            <Badge v-else-if="page.header.status" theme="blue" size="sm" :label="page.header.status" data-page-status />
          </div>
          <div class="mt-0.5 flex flex-wrap items-center gap-x-3 text-sm text-ink-gray-6">
            <span v-if="page.header.path" data-page-path-line>{{ page.header.path }}</span>
            <span v-if="page.header.organisation" data-page-org-line>at <RouterLink class="text-ink-blue-8 hover:underline" :to="pagePath('Life Person', page.header.organisation.name)">{{ page.header.organisation.title }}</RouterLink></span>
            <span v-if="page.header.role">{{ page.header.role }}</span>
            <span v-if="page.header.aliases?.length" data-page-aliases>Also called {{ page.header.aliases.join(', ') }}</span>
          </div>
        </div>
      </Card>

      <!-- a free-form page: the header and its note -->
      <Card v-if="page.note" data-page-note-body>
        <Md v-if="page.note.text" :text="page.note.text" />
        <p v-else class="text-base text-ink-gray-6">Nothing written yet.</p>
        <Button class="mt-3" label="Edit the note" icon-left="lucide-pencil" data-page-edit-note @click="openRef(`note:${name}`)" />
      </Card>

      <template v-else>
        <!-- the Brain's brief -->
        <Card data-page-brief :data-has-brief="page.brief ? 1 : 0">
          <SectionHead><span class="lucide-sparkles size-4 text-ink-gray-6" aria-hidden="true" />Brief</SectionHead>
          <template v-if="page.brief">
            <p class="text-base leading-6 text-ink-gray-9" data-brief-text>
              <template v-for="(part, i) in briefParts" :key="i"><template v-if="part.n"><Button class="mx-0.5 !h-auto !px-1 !py-0 text-sm font-medium !text-ink-blue-8" variant="ghost"
                :aria-label="`Source ${part.n}`" data-brief-source :data-n="part.n" @click="openSource(part.n)">{{ part.n }}</Button></template><template v-else>{{ part.text }}</template></template>
            </p>
            <div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-gray-6" data-brief-by>
              <span>by the Brain · as of {{ short(page.brief.on) }} · {{ page.brief.n_sources }} {{ page.brief.n_sources === 1 ? 'source' : 'sources' }}</span>
              <span v-if="page.brief.stale" data-brief-stale>· something new since</span>
              <Button v-if="canEdit" size="sm" variant="ghost" icon-left="lucide-refresh-cw" label="Rewrite" :loading="rewriting" data-brief-rewrite @click="rewrite" />
            </div>
          </template>
          <template v-else>
            <p class="text-base text-ink-gray-6" data-brief-empty>{{ page.can_rewrite ? 'The Brain has not written the brief yet.' : 'The brief is written by the Brain once something is linked to this page.' }}</p>
            <Button v-if="canEdit && page.can_rewrite" class="mt-2" size="sm" icon-left="lucide-refresh-cw" label="Write the brief now" :loading="rewriting" data-brief-rewrite @click="rewrite" />
          </template>
        </Card>

        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <!-- open -->
          <Card data-page-open>
            <SectionHead>Open</SectionHead>
            <ul v-if="openCount" class="flex flex-col gap-1">
              <li v-for="n in page.open.needs_you" :key="n.name" class="text-base" data-open-needs><RefLink class="text-ink-blue-8 hover:underline" :to="`inbox:${n.item}`">{{ n.title }}</RefLink><span class="text-sm text-ink-gray-6"> · needs you</span></li>
              <li v-for="t in page.open.tasks" :key="t.name" class="text-base" data-open-task><LinkButton class="!inline-flex !text-ink-gray-9" @click="openRef(t.ref)">{{ t.title }}</LinkButton><span v-if="t.due_date" class="text-sm text-ink-gray-6"> · due {{ short(t.due_date) }}</span></li>
              <li v-for="e in page.open.events" :key="e.name" class="text-base" data-open-event><LinkButton class="!inline-flex !text-ink-gray-9" @click="openRef(e.ref)">{{ e.title }}</LinkButton><span class="text-sm text-ink-gray-6"> · {{ short(e.starts_on) }}</span></li>
            </ul>
            <EmptyState v-else data-open-empty>Nothing is open about this.</EmptyState>
          </Card>
          <!-- people -->
          <Card data-page-people>
            <SectionHead>People</SectionHead>
            <ul v-if="page.people.length" class="flex flex-col gap-1">
              <li v-for="p in page.people" :key="p.name" class="text-base" data-page-person :data-name="p.name">
                <RouterLink class="text-ink-blue-8 hover:underline" :to="pagePath('Life Person', p.name)">{{ p.title }}</RouterLink><span v-if="p.role" class="text-sm text-ink-gray-6"> · {{ p.role }}</span><span v-else class="text-sm text-ink-gray-6"> · {{ p.why }}</span>
              </li>
            </ul>
            <EmptyState v-else data-people-empty>No one is linked yet.</EmptyState>
          </Card>
        </div>

        <!-- files -->
        <Card data-page-files>
          <SectionHead>Files <span class="text-sm text-ink-gray-6" data-files-count>{{ page.files.length }}</span></SectionHead>
          <ul v-if="page.files.length" class="flex flex-col">
            <Row as="li" bare v-for="f in page.files" :key="f.name" class="flex items-center gap-2 py-1.5" data-page-file>
              <span class="lucide-paperclip size-4 flex-none text-ink-gray-6" aria-hidden="true" />
              <a class="min-w-0 flex-1 truncate text-base text-ink-blue-8 hover:underline" :href="f.url" target="_blank" rel="noopener">{{ f.title }}</a>
              <span class="flex-none text-sm text-ink-gray-6">{{ short(f.date) }}</span>
            </Row>
          </ul>
          <EmptyState v-else data-files-empty>Files attached here, or to anything linked to this page, will show up here.</EmptyState>
        </Card>

        <!-- timeline -->
        <Card flush class="!p-0" data-page-timeline>
          <SectionHead class="px-4 pt-3">Timeline <span class="text-sm text-ink-gray-6" data-timeline-count>{{ page.timeline_total }}</span></SectionHead>
          <ul v-if="page.timeline.length" class="mt-2 flex flex-col">
            <Row as="li" bare v-for="e in page.timeline" :key="e.link" class="flex items-start gap-3 px-4 py-2.5" data-timeline-row :data-kind="e.kind" :data-ref="e.ref || ''">
              <span :class="ITEM_ICON[e.kind] || 'lucide-circle'" class="mt-0.5 size-4 flex-none text-ink-gray-6" :title="e.kind" aria-hidden="true" />
              <div class="min-w-0 flex-1">
                <LinkButton v-if="e.ref" class="text-base !font-normal !text-ink-gray-9" data-timeline-title @click="openRef(e.ref)">{{ e.title }}</LinkButton>
                <a v-else-if="e.url" class="break-words text-base text-ink-blue-8 hover:underline" :href="e.url" target="_blank" rel="noopener" data-timeline-title>{{ e.title }}</a>
                <span v-else class="break-words text-base text-ink-gray-9" data-timeline-title>{{ e.title }}</span>
              </div>
              <span class="flex-none whitespace-nowrap text-sm text-ink-gray-6" data-timeline-date>{{ short(e.date) }}</span>
              <Button v-if="canEdit" class="-my-1 flex-none" size="sm" variant="ghost" icon="lucide-x" label="Not about this" :tooltip="'Not about this'" data-timeline-remove @click="removeLink(e)" />
            </Row>
          </ul>
          <EmptyState v-else data-timeline-empty>Emails, captures, meetings, notes and tasks about {{ page.header.title }} will show up here, newest first.</EmptyState>
        </Card>

        <!-- your notes -->
        <Card data-page-notes>
          <SectionHead>Your notes</SectionHead>
          <p class="mb-2 text-sm text-ink-gray-6">Only you write here. The Brain and agents never change it.</p>
          <div v-if="canEdit" class="flex flex-col gap-2">
            <FormControl v-model="draft" type="textarea" :rows="3" placeholder="Write a note about this page" aria-label="Your notes" data-notes-input />
            <div><Button variant="solid" label="Save note" :loading="saving" :disabled="!draft.trim()" data-notes-save @click="saveNote" /></div>
          </div>
          <ul v-if="page.notes.length" class="mt-3 flex flex-col">
            <Row as="li" bare v-for="n in page.notes" :key="n.name" class="flex items-start gap-2 py-2" data-note-row>
              <div class="min-w-0 flex-1"><p class="whitespace-pre-wrap break-words text-base text-ink-gray-9" data-note-text>{{ n.text }}</p><div class="text-sm text-ink-gray-6">{{ short(n.on) }}</div></div>
              <Button v-if="canEdit" size="sm" variant="ghost" icon="lucide-trash-2" label="Delete note" :tooltip="'Delete note'" @click="dropNote(n)" />
            </Row>
          </ul>
        </Card>
      </template>
    </template>
  </div>

  <Dialog v-model:open="choose.open" title="Which page should go?" size="md" :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }]">
    <p class="mb-3 text-base text-ink-gray-7">You can pin {{ pins.limit }} pages. Unpin one to pin {{ page?.header.title }}.</p>
    <div class="flex flex-col gap-1" data-pin-choose>
      <Button v-for="p in choose.list" :key="p.doctype + p.name" class="!justify-start" variant="subtle" :label="`Unpin ${p.title}`" :icon-left="KIND_ICON[p.kind]" data-pin-choice @click="swap(p)" />
    </div>
  </Dialog>
  <NewRecord v-if="renaming" :model-value="true" title="Rename" action="Rename" :fields="[{ name: 'title', label: 'Name', required: true }]" :initial="{ title: page.header.title }" :save="doRename"
    @update:model-value="(v) => !v && (renaming = false)" />
  <NewRecord v-if="merging" :model-value="true" title="Merge with another" action="Merge" :fields="mergeFields" :save="doMerge" @update:model-value="(v) => !v && (merging = false)" />
</template>
<script setup>
import LinkButton from '@/components/ui/LinkButton.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import RefLink from '@/components/ui/RefLink.vue'
// A page (issue 111): a person, a company, a part or a note, laid out top to bottom as header, the Brain's brief with numbered sources, Open, People, Files,
// Timeline and Your notes. The Brain writes the brief and links what it files; the owner's own text is Your notes, which nothing else writes. A free-form page
// is the header and its note. Opening the page clears the "new" count on its pin.
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dialog, Dropdown, FormControl, toast } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Md from '@/components/Md.vue'
import NewRecord from '@/components/NewRecord.vue'
import PageHead from '@/components/PageHead.vue'
import { libraryData } from '@/data/library'
import { errorText, tryCall } from '@/lib/api'
import { short } from '@/lib/dates'
import { onRecordChanged, openRef } from '@/lib/pane'
import { ITEM_ICON, KIND_ICON, loadPins, pagePath, pin, pins, unpin } from '@/lib/pins'
import { canWrite, store } from '@/lib/store'

const props = defineProps({ doctype: String, name: String })
const route = useRoute()
const router = useRouter()
const STATUS_OPTIONS = [{ label: 'No status', value: '' }, ...['Prospect', 'Client', 'Partner', 'Past'].map((v) => ({ label: v, value: v }))]
const page = ref(null)
const missing = ref(false)
const draft = ref('')
const saving = ref(false)
const rewriting = ref(false)
const renaming = ref(false)
const merging = ref(false)
const mergeChoices = ref([])
const choose = ref({ open: false, list: [] })
const canEdit = computed(() => canWrite() && !store.isAgent)
const openCount = computed(() => page.value ? page.value.open.tasks.length + page.value.open.events.length + page.value.open.needs_you.length : 0)

// the brief's text with its [n] markers as buttons
const briefParts = computed(() => (page.value?.brief?.md || '').split(/(\[\d+\])/).filter(Boolean).map((t) => (/^\[\d+\]$/.test(t) ? { n: Number(t.slice(1, -1)) } : { text: t })))

async function load() {
  try {
    page.value = await libraryData.pages.get({ doctype: props.doctype, name: props.name })
    missing.value = false
  } catch (e) {
    page.value = null
    missing.value = true
  }
}
async function opened() {
  const res = await tryCall(() => libraryData.pages.visit({ doctype: props.doctype, name: props.name }))
  await loadPins()
  if (res?.offer_pin) toast.info(`Pin ${page.value?.header.title || 'this page'}?`, { duration: 15000, action: { label: 'Pin it', onClick: () => togglePin() } })
}
function openSource(n) {
  const s = (page.value.brief.sources || []).find((x) => x.n === n)
  if (!s) return
  if (s.ref) openRef(s.ref)
  else if (s.url) window.open(s.url, '_blank', 'noopener')
}

async function togglePin() {
  const { doctype, name } = props
  if (page.value.pinned) { await unpin(doctype, name); page.value.pinned = false; return }
  const res = await pin(doctype, name)
  if (res?.refused) choose.value = { open: true, list: res.choose_to_unpin }
  else if (res) page.value.pinned = true
}
async function swap(p) {
  const res = await pin(props.doctype, props.name, `${p.doctype}:${p.name}`)
  choose.value.open = false
  if (res?.pinned) page.value.pinned = true
}

async function setStatus(v) {
  const res = await tryCall(() => libraryData.pages.set_status({ name: props.name, status: v || undefined }))
  if (res) page.value.header.status = res.status
}
async function rewrite() {
  rewriting.value = true
  try {
    const res = await libraryData.pages.rewrite({ doctype: props.doctype, name: props.name })
    if (res.written) await load()
    else toast.info(res.capped ? `The month's AI cap is reached, so the brief waits. ${res.reason}` : `The brief was not written: ${res.reason}.`)
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    rewriting.value = false
  }
}
async function removeLink(e) {
  const res = await tryCall(() => libraryData.pages.remove_link({ link: e.link }), 'Taken off this page. The Brain will not link it again.')
  if (res) await load()
}
async function saveNote() {
  saving.value = true
  const res = await tryCall(() => libraryData.pages.add_note({ doctype: props.doctype, name: props.name, text: draft.value }))
  saving.value = false
  if (res) { page.value.notes = res.notes; draft.value = '' }
}
async function dropNote(n) {
  const res = await tryCall(() => libraryData.pages.delete_note({ doctype: props.doctype, name: props.name, note: n.name }))
  if (res) page.value.notes = res.notes
}

const menu = computed(() => [
  { label: 'Rename', icon: 'lucide-pencil', onClick: () => { renaming.value = true } },
  ...(props.doctype === 'Life Person' ? [{ label: 'Merge with another', icon: 'lucide-merge', onClick: openMerge }] : []),
  { label: 'Archive', icon: 'lucide-archive', onClick: archive },
])
const doRename = async (v) => {
  await libraryData.pages.rename({ doctype: props.doctype, name: props.name, title: v.title })
  await load()
  await loadPins()
}
async function openMerge() {
  const res = await tryCall(() => libraryData.people.list({ space: store.space, kind: page.value.header.kind === 'company' ? 'Organisation' : 'Person', page_length: 100 }))
  mergeChoices.value = (res?.rows || []).filter((r) => r.name !== props.name).map((r) => ({ label: r.title, value: r.name }))
  merging.value = true
}
const mergeFields = computed(() => [{ name: 'into', label: `Merge ${page.value?.header.title} into`, options: mergeChoices.value, required: true, help: 'Its emails, other names and notes move to the one you choose, and this page goes.' }])
async function doMerge(v) {
  await libraryData.pages.merge({ name: props.name, into: v.into })
  await loadPins()
  router.replace(pagePath('Life Person', v.into))
}
async function archive() {
  const res = await tryCall(() => libraryData.pages.archive({ doctype: props.doctype, name: props.name }), 'Archived.')
  if (res) { await loadPins(); router.push('/library/pages') }
}

watch(() => [props.doctype, props.name], async () => { await load(); opened() })
onRecordChanged(load)
onMounted(async () => { await load(); if (page.value) opened() })
</script>
