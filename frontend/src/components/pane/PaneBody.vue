<template>
  <header class="flex flex-none flex-col gap-2.5 border-b border-outline-gray-1 px-4 pb-3 md:px-5" :class="phone ? 'pt-0' : 'pt-3.5'">
    <div class="flex items-start gap-2">
      <div class="min-w-0 flex-1">
        <div class="text-sm text-ink-gray-6">{{ label }}</div>
        <h2 class="break-words text-lg-semibold text-ink-gray-9" data-pane-title>{{ meta.title || (missing ? 'Not found' : 'Loading…') }}</h2>
      </div>
      <Button v-if="meta.fullPage" label="Open full page" :route="meta.fullPage" data-pane-full />
      <Button icon="lucide-x" label="Close" tooltip="Close" data-pane-close @click="closePane" />
    </div>
    <div v-if="meta.area || meta.project || meta.sub" class="flex flex-wrap items-center gap-2">
      <Button v-if="meta.area" size="sm" variant="outline" icon-left="lucide-folder" :label="meta.area_name || 'Area'" :route="`/areas/${meta.area}`" />
      <Button v-if="meta.project" size="sm" variant="outline" icon-left="lucide-chart-no-axes-column" :label="meta.project_title || meta.project" @click="openRef('project:' + meta.project)" />
      <span v-if="meta.sub" class="text-sm text-ink-gray-6">{{ meta.sub }}</span>
    </div>
  </header>
  <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-8 pt-4 md:px-5" data-pane-body>
    <Alert v-if="meta.archived" title="This record is archived. It is shown read-only."
      :primary-action="meta.canRestore ? { label: 'Restore', onClick: () => $emit('restore') } : undefined" />
    <Card v-if="missing"><Empty title="This record was not found." hint="It may be in another space, or it was removed." /></Card>
    <component :is="VIEW[cur.type]" v-else :key="cur.ref + ':' + stamp" :name="cur.name" :type="cur.type" @meta="(m) => $emit('meta', m)" @missing="$emit('missing')"
      @changed="$emit('changed')" @close="closePane" />
  </div>
</template>
<script setup>
// The inside of the record pane, the same on desktop and phone: a header with the record's type, title, filing and
// buttons, then the pane content for that type of record.
import { defineAsyncComponent } from 'vue'
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
import PlainPane from './PlainPane.vue'
import { closePane, openRef } from '@/lib/pane'

defineProps({ cur: Object, meta: Object, label: String, missing: Boolean, stamp: Number, phone: Boolean })
defineEmits(['meta', 'missing', 'changed', 'restore'])
const VIEW = { task: TaskPane, inbox: defineAsyncComponent(() => import('../ReviewBody.vue')), note: NotePane, vault: VaultPane, project: ProjectPane,
  goal: GoalPane, page: PagePane, chat: ChatPane, event: EntryPane, date: EntryPane, day: DayPane, checkin: PlainPane, month: PlainPane }
</script>
