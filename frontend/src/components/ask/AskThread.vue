<template>
  <div class="flex flex-col gap-4" data-ask-thread>
    <template v-for="(m, i) in ask.messages" :key="i">
      <div v-if="m.role === 'user'" class="flex max-w-[85%] flex-col gap-1 self-end rounded-5 bg-surface-gray-2 px-3.5 py-2 text-base text-ink-gray-9" data-ask-question>{{ m.text }}
        <span v-for="f in m.attached || []" :key="f" class="flex items-center gap-1.5 text-sm text-ink-gray-7" data-ask-attached><span class="lucide-paperclip size-3.5" aria-hidden="true" />{{ f }}</span></div>
      <div v-else class="flex flex-col gap-3" data-ask-answer :data-status="m.status">
        <div v-if="m.status === 'Error'"><Alert theme="red" :title="m.error || 'The answer could not be written.'" data-ask-error /></div>
        <template v-else>
          <Md v-if="m.text" :text="m.text" :cites="m.cited || []" @cite="(n) => openCite(m, n)" />
          <div v-if="m.status === 'Working'" class="flex items-center gap-2 text-sm text-ink-gray-6" aria-live="polite" data-ask-working>
            <LoadingIndicator class="size-3.5" /><span v-if="m.reading" data-ask-reading>{{ m.reading }}</span><template v-else>{{ m.text ? 'Writing…' : 'Reading your records…' }}</template></div>
          <div v-if="m.done && m.done.length" class="flex flex-col gap-1.5 rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5" data-ask-done>
            <div class="text-sm text-ink-gray-6">Done</div>
            <div v-for="(d, j) in m.done" :key="j" class="flex flex-wrap items-center gap-x-3 gap-y-1 text-base text-ink-gray-9" data-ask-done-line :data-undone="d.undone ? 1 : 0">
              <span class="min-w-0 flex-[1_1_240px]" :class="d.undone && 'text-ink-gray-5 line-through'">{{ d.text }}</span>
              <a v-if="d.pane && !d.undone" href="#" class="text-sm text-ink-blue-8 hover:underline focus-visible:focus-ring" data-ask-done-open @click.prevent="openPane(d.pane)">Change</a>
              <span v-if="d.undone" class="text-sm text-ink-gray-6">Undone</span>
              <RouterLink v-if="d.kind === 'rule' && !d.undone" class="text-sm text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="{ path: '/settings', query: { tab: 'rules' } }" data-ask-rule-change>Change</RouterLink>
              <Button v-if="!d.undone && d.undo && canWrite()" size="sm" variant="subtle" label="Undo" data-ask-undo @click="undoDone(m, j)" />
            </div>
          </div>
          <!-- a message Chat wrote for a person: nothing goes until Send -->
          <div v-for="d in m.drafts || []" :key="d.name" class="flex flex-col gap-2 rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5" data-ask-draft :data-status="d.status">
            <div class="flex flex-wrap items-center gap-x-2 text-sm text-ink-gray-6"><span>To</span><span class="text-base text-ink-gray-9" data-ask-draft-to>{{ d.to }}<template v-if="d.address"> · {{ d.address }}</template></span>
              <Badge v-if="d.status === 'Sent'" theme="green" label="Sent" /></div>
            <div v-if="d.channel === 'email'" class="text-base font-medium text-ink-gray-9" data-ask-draft-subject>{{ d.subject }}</div>
            <FormControl v-if="edits[d.name] !== undefined" v-model="edits[d.name]" type="textarea" :rows="6" data-ask-draft-text />
            <div v-else class="whitespace-pre-wrap break-words text-base text-ink-gray-9" data-ask-draft-body>{{ d.body }}</div>
            <div v-if="d.needs_address && d.status === 'Draft'" class="flex flex-wrap items-center gap-2" data-ask-draft-address>
              <TextInput v-model="addresses[d.name]" class="min-w-0 flex-[1_1_200px]" placeholder="Their email address" />
              <Button size="sm" variant="subtle" label="Save address" :disabled="!addresses[d.name]" @click="draftAddress(d, addresses[d.name])" />
            </div>
            <div v-if="d.status === 'Sent'" class="text-sm text-ink-gray-6" data-ask-draft-sent>Sent. A sent email cannot be taken back.</div>
            <div v-else-if="canWrite()" class="flex flex-wrap items-center gap-2">
              <Button v-if="edits[d.name] === undefined" size="sm" variant="solid" label="Send" :disabled="d.needs_address" :loading="busy[d.name]" data-ask-draft-send @click="send(m, d)" />
              <Button v-else size="sm" variant="solid" label="Save" data-ask-draft-save @click="saveEdit(d)" />
              <Button v-if="edits[d.name] === undefined" size="sm" variant="subtle" label="Edit" data-ask-draft-edit @click="edits[d.name] = d.body" />
              <Button v-else size="sm" variant="subtle" label="Cancel" @click="delete edits[d.name]" />
              <Button size="sm" variant="subtle" label="Drop" data-ask-draft-drop @click="draftDrop(m, d)" />
            </div>
          </div>
          <!-- whose is this card: one question with tappable answers, then it is saved -->
          <div v-for="q in m.questions || []" :key="q.index" class="flex flex-col gap-2 rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5" data-ask-question-card>
            <div class="text-base text-ink-gray-9">{{ q.text }} <span class="text-sm text-ink-gray-6">{{ q.file_name }}</span></div>
            <div class="flex flex-wrap gap-2"><Button v-for="o in q.options" :key="o.value" size="sm" variant="subtle" :label="o.label" data-ask-holder @click="answerCard(m, q.index, o.value)" /></div>
          </div>
          <div v-if="m.cited && m.cited.length" class="text-sm text-ink-gray-6" data-ask-sources>Sources:
            <template v-for="(c, j) in m.cited" :key="c.n"><span v-if="j"> · </span><a href="#" class="text-ink-blue-8 hover:underline focus-visible:focus-ring" :data-ask-cite="c.n"
              @click.prevent="openCite(m, c.n)">{{ c.n }} {{ c.title }}</a></template>
          </div>
        </template>
      </div>
    </template>
    <Alert v-if="ask.refusal" :theme="ask.refusal.error === 'cap' ? 'amber' : 'gray'" :title="ask.refusal.error_text" data-ask-refusal :data-refusal="ask.refusal.error">
      <template #description>
        <template v-if="ask.refusal.error === 'not_set_up'">
          <RouterLink v-if="store.isAdmin" class="text-ink-blue-8 hover:underline" :to="{ path: '/settings', query: { tab: 'advanced', part: 'ai' } }" data-ask-key-link @click="ask.open = false">Open Settings › AI</RouterLink>
          <template v-else>An administrator adds the key in Settings › AI.</template></template>
        <template v-else-if="ask.refusal.error === 'cap'">{{ ask.refusal.spend?.text }}. The cap is in
          <RouterLink class="text-ink-blue-8 hover:underline" :to="{ path: '/settings', query: { tab: 'advanced' } }" @click="ask.open = false">Settings, Advanced, AI key and cost</RouterLink>.</template>
        <template v-else-if="ask.refusal.error === 'off'">The owner can turn it on in
          <RouterLink v-if="manySpaces" class="text-ink-blue-8 hover:underline" :to="{ path: '/settings', query: { tab: 'members', view: 'spaces' } }" @click="ask.open = false">Settings, Members, Spaces</RouterLink>
          <RouterLink v-else class="text-ink-blue-8 hover:underline" :to="{ path: '/settings', query: { tab: 'advanced' } }" @click="ask.open = false">Settings, Advanced</RouterLink>.</template>
      </template>
    </Alert>
    <AskSearchHits v-if="ask.refusal && ask.refusal.error === 'not_set_up' && lastQuestion" :query="lastQuestion" />
  </div>
</template>
<script setup>
// One Chat thread: messages on the right, answers with numbered citations, what Chat did (each line with Change) and the sources.
// Clicking a citation opens the record in the pane.
import { computed, reactive } from 'vue'
import { Alert, Badge, Button, FormControl, LoadingIndicator, TextInput } from 'frappe-ui'
import Md from '../Md.vue'
import { manySpaces } from '@/lib/lens'
import { canWrite, store } from '@/lib/store'
import AskSearchHits from './AskSearchHits.vue'
import { answerCard, ask, draftAddress, draftDrop, draftEdit, draftSend, openCite, openPane, undoDone } from '@/lib/ask'
const edits = reactive({})
const addresses = reactive({})
const busy = reactive({})
async function send(m, d) { busy[d.name] = true; try { await draftSend(m, d) } finally { busy[d.name] = false } }
async function saveEdit(d) { if (await draftEdit(d, edits[d.name])) delete edits[d.name] }
const lastQuestion = computed(() => [...ask.messages].reverse().find((m) => m.role === 'user')?.text || '')
</script>
