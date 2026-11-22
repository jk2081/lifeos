<template>
  <header class="flex flex-none flex-col gap-2.5 border-outline-gray-1 px-4 pb-3 md:px-5" :class="[phone ? 'pt-0' : 'pt-3.5', tabs.length > 1 ? '' : 'border-b']">
    <!-- the actions on their own line with Close pinned at the end; the kind and title below at the pane's full width,
         so the title never shares a row with buttons -->
    <div class="flex items-start gap-1.5">
      <div class="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-1.5" data-pane-actions>
      <Button v-if="!store.isAgent && ASKABLE[cur.type] && !missing" :size="btnSize" icon-left="lucide-sparkles" :label="phone ? 'Ask' : 'Ask about this'" data-pane-ask
        @click="askAbout(ASKABLE[cur.type], cur.name, meta.title)" />
      <!-- the sensitive mark (UX fixes, set 6): a lock while it is on; anyone who may edit marks it, only the space's owner unmarks it -->
      <Button v-if="meta.sensitive && !store.isAgent" :size="btnSize" :icon-left="meta.sensitive.on ? 'lucide-lock' : 'lucide-lock-open'" :variant="meta.sensitive.on ? 'subtle' : 'ghost'"
        :label="phone ? '' : meta.sensitive.on ? 'Sensitive' : 'Mark sensitive'" :tooltip="meta.sensitive.on ? 'Sensitive: follows the Vault rules. Click to unmark (the space owner only).' : 'Mark sensitive'"
        :aria-pressed="meta.sensitive.on" data-pane-sensitive @click="toggleSensitive" />
      <Button v-if="meta.someday" :size="btnSize" icon-left="lucide-clock" :label="phone ? 'Someday' : 'Move to Someday'" data-pane-someday @click="toSomeday" />
      <Button v-if="meta.fullPage" :size="btnSize" label="Open full page" :route="meta.fullPage" data-pane-full />
      </div>
      <Button class="shrink-0" :size="btnSize" icon="lucide-x" label="Close" tooltip="Close" data-pane-close @click="closePane" />
    </div>
    <div class="min-w-0">
      <div class="text-sm text-ink-gray-6">{{ label }}</div>
      <h2 class="break-words text-lg-semibold text-ink-gray-9" data-pane-title>{{ meta.title || (missing ? 'Not found' : 'Loading…') }}</h2>
    </div>
    <div v-if="meta.area || meta.goal || meta.sub" class="flex flex-wrap items-center gap-2">
      <Button v-if="meta.area" size="sm" variant="outline" icon-left="lucide-folder" :label="meta.area_name || 'Area'" :route="`/areas/${meta.area}`" />
      <Button v-if="meta.goal" size="sm" variant="outline" icon-left="lucide-target" :label="meta.goal_title || meta.goal" data-pane-goal @click="openRef('goal:' + meta.goal)" />
      <span v-if="meta.sub" class="text-sm text-ink-gray-6">{{ meta.sub }}</span>
    </div>
  </header>
  <!-- the pane's own tabs (ptab=), under the header; a pane with one tab shows no bar -->
  <TabBar v-if="tabs.length > 1" class="flex-none" list-class="px-4 md:px-5" :tabs="tabs" :model-value="ptab.current.value"
    :label="label + ' sections'" :level="2" data-pane-tabs @update:model-value="ptab.set" />
  <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-8 pt-4 md:px-5" data-pane-body>
    <Alert v-if="meta.archived" title="This record is archived. It is shown read-only."
      :primary-action="meta.canRestore ? { label: 'Restore', onClick: () => $emit('restore') } : undefined" />
    <Card v-if="missing"><Empty title="This record was not found." hint="It may be in another space, or it was removed." /></Card>
    <component :is="VIEW[cur.type]" v-else :key="cur.ref + ':' + stamp" :name="cur.name" :type="cur.type" :tab="tabs.length ? ptab.current.value : undefined" @meta="(m) => $emit('meta', m)" @missing="$emit('missing')"
      @changed="$emit('changed')" @close="closePane" />
  </div>
</template>
<script setup>
// The inside of the record pane, the same on desktop and phone: a header with the record's type, title, filing and
// buttons, then the pane content for that type of record.
import { computed, defineAsyncComponent } from 'vue'
import TabBar from '../TabBar.vue'
import { useUrlTab } from '@/lib/tabs'
import { Alert, Button } from 'frappe-ui'
import Card from '../ui/Card.vue'
import Empty from '../Empty.vue'
import TaskPane from './TaskPane.vue'
import VaultPane from './VaultPane.vue'
import ProjectPane from './ProjectPane.vue'
import GoalPane from './GoalPane.vue'
import PagePane from './PagePane.vue'
import ChatPane from './ChatPane.vue'
import EntryPane from './EntryPane.vue'
import DayPane from './DayPane.vue'
import NotePane from './NotePane.vue'
import SourcePane from './SourcePane.vue'
import ChangePane from './ChangePane.vue'
import PlainPane from './PlainPane.vue'
import { closePane, openRef } from '@/lib/pane'
import { park } from '@/lib/someday'
import { askAbout } from '@/lib/ask'
import { store } from '@/lib/store'
import { api, tryCall } from '@/lib/api'

const props = defineProps({ cur: Object, meta: Object, label: String, missing: Boolean, stamp: Number, phone: Boolean })
// Each kind of record says its tabs in its meta: [{ value, label, count }]. The open one is ptab= in the URL; the first is the default.
const tabs = computed(() => (props.missing ? [] : props.meta.tabs || []))
// the header's buttons: small beside a desktop pane's title, full size (40 px) to tap on a phone
const btnSize = computed(() => (props.phone ? 'md' : 'sm'))
const ptab = useUrlTab('ptab', tabs, { replace: true })
const emit = defineEmits(['meta', 'missing', 'changed', 'restore', 'reload'])
// "Ask about this": the record and the records linked to it are the question's scope
const ASKABLE = { task: 'Life Task', note: 'Life Note', goal: 'Life Goal', chat: 'Life Chat Log', source: 'Life Inbox Item',
  inbox: 'Life Inbox Item', page: 'Life Journal Page', vault: 'Life Vault Document' }
async function toggleSensitive() {
  const s = props.meta.sensitive
  if (await tryCall(() => api('library.set_sensitive', { doctype: s.doctype, name: s.name, sensitive: s.on ? 0 : 1 }), s.on ? 'No longer sensitive.' : 'Marked sensitive.')) emit('reload')
}
async function toSomeday() {
  if (await park(props.meta.someday.doctype, props.meta.someday.name, props.meta.title)) emit('reload')
}
const VIEW = { source: SourcePane, change: ChangePane, task: TaskPane, inbox: defineAsyncComponent(() => import('../ReviewBody.vue')), note: NotePane, vault: VaultPane, project: ProjectPane, // ProjectPane hands over to the goal the project became
  goal: GoalPane, page: PagePane, chat: ChatPane, event: EntryPane, date: EntryPane, day: DayPane, checkin: PlainPane, month: PlainPane }
</script>
