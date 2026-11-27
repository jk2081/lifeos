<template>
  <Dialog v-model:open="open" :title="task ? 'Hand off' : 'Hand off to someone'" size="sm" data-handoff-dialog
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: how === 'send' ? 'Send and wait' : how === 'draft' ? 'Draft and wait' : 'Wait on them', variant: 'solid', loading: busy, onClick: go }]">
    <div class="flex flex-col gap-3">
      <PersonPicker v-model="pick" label="Who" :space="props.space || store.space" placeholder="Who is it?" data-handoff-person />
      <TextInput v-if="!task" v-model="what" label="What they owe you" placeholder="The ITR draft" data-handoff-what />
      <DatePicker v-model="checkBy" format="D MMM YYYY" label="Look again on" clearable placeholder="Life OS picks a day" data-handoff-date />
      <div>
        <div class="mb-1.5 text-sm text-ink-gray-6">Message</div>
        <TabButtons v-model="how" :options="HOWS" data-handoff-how />
        <p class="mt-1.5 text-sm text-ink-gray-6">{{ HINT[how] }}</p>
      </div>
      <FormControl v-if="how !== 'track'" type="select" label="By" :model-value="channel" :options="CHANNELS" data-handoff-channel @update:model-value="(v) => (channel = v)" />
    </div>
  </Dialog>
</template>
<script setup>
// Hand off (issue 130): who owes what, by when, and whether a message goes with it. Just track is the default and sends nothing; Draft a message writes one for the owner to
// send, edit or drop; Send emails at once. Life OS never sends WhatsApp: it makes the link.
import { ref, watch } from 'vue'
import { DatePicker, Dialog, FormControl, TabButtons, TextInput, toast } from 'frappe-ui'
import { tryCall } from '@/lib/api'
import { itemData } from '@/data/item'
import { openRef, recordChanged } from '@/lib/pane'
import { store } from '@/lib/store'
import PersonPicker from '@/components/ui/PersonPicker.vue'

const props = defineProps({ task: { type: String, default: '' }, space: { type: String, default: '' }, person: { type: String, default: '' }, what: { type: String, default: '' } })
const open = defineModel({ type: Boolean, default: false })
const emit = defineEmits(['done'])
const HOWS = [{ label: 'Just track', value: 'track' }, { label: 'Draft a message', value: 'draft' }, { label: 'Send', value: 'send' }]
const CHANNELS = [{ label: 'Email', value: 'email' }, { label: 'WhatsApp', value: 'whatsapp' }]
const HINT = { track: 'Nothing is sent. You are only noting who owes you what.', draft: 'A message is written for you to send, edit or drop.', send: 'The email goes now. WhatsApp is always a link you send yourself.' }
const pick = ref(props.person)
const what = ref(props.what)
const checkBy = ref('')
const how = ref('track')
const channel = ref('email')
const busy = ref(false)

watch(open, (on) => { if (on) { pick.value = props.person; what.value = props.what; checkBy.value = ''; how.value = 'track'; channel.value = 'email' } })

async function go({ close }) {
  const who = pick.value
  if (!who) return toast.error('Say who it is handed to.')
  if (!props.task && !what.value.trim()) return toast.error('Say what they owe you.')
  busy.value = true
  const out = await tryCall(() => itemData.tasks.hand_off({ person: who, what: what.value.trim() || undefined, check_by: checkBy.value || undefined, how: how.value, channel: channel.value,
    task: props.task || undefined, space: props.space || store.space }))
  busy.value = false
  if (!out) return
  toast.success(out.sent ? `Sent to ${out.who}. Waiting on them.` : out.how === 'draft' ? `Drafted for ${out.who}. Nothing is sent yet.` : `Waiting on ${out.who}. Nothing was sent.`)
  close()
  recordChanged('task:' + out.task)
  emit('done', out)
  if (out.how === 'draft' && !props.task) openRef('task:' + out.task, { push: true })
}
</script>
