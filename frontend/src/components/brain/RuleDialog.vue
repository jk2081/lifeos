<template>
  <Dialog v-model:open="open" :title="rule ? 'Change this rule' : 'Add a rule'" size="lg" data-rule-dialog
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: rule ? 'Save' : 'Add rule', variant: 'solid', loading: busy, onClick: submit }]">
    <div class="flex flex-col gap-4">
      <div class="flex flex-col gap-2">
        <SectionHead>When a capture…</SectionHead>
        <div class="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
          <FormControl v-model="v.sender" label="Is from this address" placeholder="sales2@rungamattee.com" data-rule-sender />
          <FormControl v-model="v.domain" label="Or anyone at this domain" placeholder="rungamattee.com" data-rule-domain />
          <FormControl v-model="v.source" type="select" label="Comes from" :options="SOURCES" data-rule-source />
          <FormControl v-model="v.item_kind" label="Is a kind of" placeholder="Chat, Email Digest" data-rule-kind />
          <FormControl v-model="v.title_words" label="Has these words in the title" placeholder="SALE, invoice" data-rule-words />
          <FormControl v-model="v.attachment_type" label="Has an attachment of type" placeholder="pdf" data-rule-attachment />
        </div>
      </div>
      <div class="flex flex-col gap-2">
        <SectionHead>…then</SectionHead>
        <div class="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
          <FormControl v-model="v.action" type="select" label="Do this" :options="ACTIONS" data-rule-action />
          <FormControl v-if="v.action === 'File'" v-model="v.file_as" type="select" label="File it as" :options="FILE_AS" data-rule-file-as />
        </div>
        <div v-if="v.action === 'File'" class="flex flex-wrap items-end gap-3">
          <div v-if="!v.no_area" class="flex flex-col gap-1"><span class="text-sm text-ink-gray-6">Under</span>
            <AreaPicker v-model="v.area" placeholder="Choose an area or part" data-rule-area /></div>
          <Checkbox v-model="v.no_area" label="No area" data-rule-no-area />
        </div>
        <Checkbox v-model="v.never_page" label="Never make a page for the sender" data-rule-never-page />
      </div>
      <p v-if="error" class="text-sm text-ink-red-8" role="alert" data-rule-error>{{ error }}</p>
    </div>
  </Dialog>
</template>
<script setup>
import SectionHead from '@/components/ui/SectionHead.vue'
// The form behind "+ Add a rule" and a rule's Change > Edit (issue 117): what a capture is like, then what to do with it.
import { reactive, ref, watch } from 'vue'
import { Checkbox, Dialog, FormControl } from 'frappe-ui'
import AreaPicker from '@/components/ui/AreaPicker.vue'
import { errorText } from '@/lib/api'
import { brainData } from '@/data/brain'
import { store } from '@/lib/store'

const props = defineProps({ rule: { type: Object, default: null }, source: { type: String, default: '' } })
const emit = defineEmits(['saved'])
const open = defineModel('open', { type: Boolean, default: false })
const SOURCES = [{ label: 'Any source', value: '' }, { label: 'Gmail', value: 'gmail' }, { label: 'Google Calendar', value: 'google-calendar' }, { label: 'Claude', value: 'claude' },
  { label: 'Your assistant', value: 'hermes' }, { label: 'Capture', value: 'upload' }]
const ACTIONS = [{ label: 'File it', value: 'File' }, { label: 'Not needed (drop)', value: 'Drop' }, { label: 'Always ask me', value: 'Ask' }]
const FILE_AS = [{ label: 'As it is', value: '' }, { label: 'A chat', value: 'Chat' }, { label: 'A note', value: 'Note' }, { label: 'A report', value: 'Report' }, { label: 'A task', value: 'Task' }]
const blank = () => ({ sender: '', domain: '', source: props.source || '', item_kind: '', title_words: '', attachment_type: '', action: 'File', file_as: '', area: null, no_area: false, never_page: false })
const v = reactive(blank())
const busy = ref(false)
const error = ref('')
watch(open, (o) => {
  if (!o) return
  error.value = ''
  Object.assign(v, blank(), props.rule ? Object.fromEntries(Object.entries(props.rule.values).map(([k, x]) => [k, k === 'no_area' || k === 'never_page' ? !!x : x ?? (k === 'area' ? null : '')])) : {})
})
async function submit({ close }) {
  busy.value = true
  error.value = ''
  const values = { ...v, no_area: v.no_area ? 1 : 0, never_page: v.never_page ? 1 : 0, area: v.no_area ? null : v.area }
  try {
    if (props.rule) await brainData.rules.change({ rule: props.rule.name, what: 'edit', values: JSON.stringify(values) })
    else await brainData.rules.add({ ...values, space: store.space })
    emit('saved')
    close()
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}
</script>
