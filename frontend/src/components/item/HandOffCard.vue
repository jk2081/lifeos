<template>
  <section v-if="d && (d.how || d.looks_done || d.status === 'Waiting')" class="flex flex-col gap-3" data-handoff-card>
    <SectionHead>Handed off</SectionHead>
    <Card v-if="d.looks_done" class="flex flex-col gap-2 !border-outline-green-3 !bg-surface-green-1" data-looks-done>
      <div class="text-base-medium text-ink-gray-9">Looks done: {{ d.looks_done.note || d.who }}</div>
      <div class="flex flex-wrap items-center gap-2">
        <Button variant="solid" label="Confirm" data-looks-done-confirm :disabled="!writable" @click="confirm" />
        <Button label="Not yet" data-looks-done-not-yet :disabled="!writable" @click="no" />
        <Button v-if="d.looks_done.item" variant="ghost" label="See the reply" @click="openRef('inbox:' + d.looks_done.item)" />
      </div>
    </Card>
    <Card class="flex flex-col gap-2">
      <dl class="flex flex-col gap-1 text-base">
        <div class="flex gap-3"><dt class="w-28 flex-none text-sm text-ink-gray-6">Waiting on</dt><dd class="min-w-0 break-words text-ink-gray-9" data-handoff-who>{{ d.who }}</dd></div>
        <div v-if="d.check_by" class="flex gap-3"><dt class="w-28 flex-none text-sm text-ink-gray-6">Look again</dt><dd class="text-ink-gray-9">{{ short(d.check_by, true) }}</dd></div>
        <div class="flex gap-3"><dt class="w-28 flex-none text-sm text-ink-gray-6">How</dt><dd class="text-ink-gray-9" data-handoff-how>{{ howText }}</dd></div>
        <div v-if="d.ask" class="flex gap-3"><dt class="w-28 flex-none text-sm text-ink-gray-6">You asked</dt><dd class="min-w-0 break-words text-ink-gray-9" data-handoff-ask>{{ d.ask }}</dd></div>
      </dl>
    </Card>
    <div v-if="d.message" class="flex flex-col gap-2" data-handoff-message>
      <div class="text-sm-medium text-ink-gray-7">{{ d.how === 'sent' ? 'Message sent' : 'Message drafted' }}</div>
      <Textarea v-if="d.how === 'draft' && editing" v-model="text" :rows="6" aria-label="Message" data-handoff-text />
      <Card v-else class="whitespace-pre-wrap break-words text-base text-ink-gray-9" data-handoff-text-shown>{{ d.message }}</Card>
      <div v-if="d.how === 'draft' && writable" class="flex flex-wrap items-center gap-2">
        <Button v-if="d.channel !== 'whatsapp'" variant="solid" label="Send" icon-left="lucide-send" data-handoff-send :loading="busy" @click="send" />
        <Button v-else-if="d.whatsapp" variant="solid" label="Open WhatsApp" icon-left="lucide-message-circle" data-handoff-whatsapp :data-href="d.whatsapp" @click="openWhatsapp" />
        <Button v-if="!editing" label="Edit" data-handoff-edit @click="edit" />
        <Button v-else label="Save" data-handoff-save :loading="busy" @click="saveEdit" />
        <Button variant="ghost" label="Discard" data-handoff-discard @click="discard" />
      </div>
      <div v-if="d.needs_phone && writable" class="flex flex-wrap items-end gap-2" data-handoff-phone>
        <TextInput v-model="phone" label="Their phone, to open WhatsApp" placeholder="+91 98765 43210" class="min-w-0 flex-1" />
        <Button label="Save phone" :disabled="!phone.trim()" @click="savePhone" />
      </div>
      <p v-if="d.channel === 'email' && d.how === 'draft' && !d.has_email" class="text-sm text-ink-amber-9">They have no email yet. Add it on their page.</p>
    </div>
    <div v-if="d.activity?.length" data-handoff-activity>
      <div class="mb-1 text-sm-medium text-ink-gray-7">Replies and nudges</div>
      <Card flush class="!px-4"><Row v-for="(a, i) in d.activity" :key="i" class="!items-center" data-handoff-line><span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ a.text }}</span><span class="flex-none text-sm text-ink-gray-6">{{ short(a.on) }}</span></Row></Card>
    </div>
    <div v-if="writable && d.status === 'Waiting'" class="flex flex-wrap items-center gap-2">
      <Button v-if="d.nudges < 2" label="Nudge" icon-left="lucide-bell" data-handoff-nudge @click="nudgeNow" />
      <Button v-if="d.person" variant="ghost" label="Open their page" @click="openRef('person:' + d.person)" />
    </div>
  </section>
</template>
<script setup>
// The hand-off part of the task layer (issue 130): what was asked in the owner's words, the message sent or drafted (Send, Edit, Discard, or the WhatsApp link), the replies and
// nudges, and Nudge. The Hand off button itself is in TaskPane's details.
import { computed, onMounted, ref, watch } from 'vue'
import { Button, Textarea, TextInput, toast } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { tryCall } from '@/lib/api'
import { itemData } from '@/data/item'
import { confirmDone, nudge, notYet } from '@/lib/handoff'
import { onRecordChanged, openRef, recordChanged } from '@/lib/pane'
import { short } from '@/lib/dates'

const props = defineProps({ task: String, writable: Boolean })
const emit = defineEmits(['changed'])
const d = ref(null)
const editing = ref(false)
const text = ref('')
const phone = ref('')
const busy = ref(false)
const howText = computed(() => ({ track: 'Tracking only. Nothing was sent.', draft: d.value.channel === 'whatsapp' ? 'WhatsApp message drafted. You send it.' : 'Email drafted. Not sent yet.', sent: 'Email sent.' }[d.value.how] || 'Waiting on them'))

async function load() {
  const res = await tryCall(() => itemData.tasks.handoff_get({ task: props.task }))
  if (res) d.value = res
}
const changed = () => { recordChanged('task:' + props.task); emit('changed'); return load() }
const confirm = async () => { if (await confirmDone(props.task, d.value.ask || '')) await load(); emit('changed') }
const no = async () => { if (await notYet(props.task)) await load(); emit('changed') }
const edit = () => { text.value = d.value.message; editing.value = true }
async function saveEdit() {
  busy.value = true
  const out = await tryCall(() => itemData.tasks.handoff_edit({ task: props.task, text: text.value }), 'Saved.')
  busy.value = false
  if (out) { editing.value = false; await changed() }
}
async function send() {
  busy.value = true
  const out = await tryCall(() => itemData.tasks.handoff_send({ task: props.task, text: editing.value ? text.value : undefined }), 'Sent.')
  busy.value = false
  if (out) { editing.value = false; await changed() }
}
async function discard() {
  if (await tryCall(() => itemData.tasks.handoff_discard({ task: props.task }), 'Draft dropped. Still waiting.')) { editing.value = false; await changed() }
}
async function savePhone() {
  if (await tryCall(() => itemData.tasks.person_phone({ person: d.value.person, phone: phone.value }), 'Phone saved.')) { phone.value = ''; await changed() }
}
function openWhatsapp() {
  window.open(d.value.whatsapp, '_blank', 'noopener,noreferrer')
  toast.info('WhatsApp has the message ready. You send it yourself.')
}
async function nudgeNow() { if (await nudge(props.task, d.value.channel || undefined)) await load() }
onRecordChanged(load)
watch(() => props.task, load)
onMounted(load)
</script>
