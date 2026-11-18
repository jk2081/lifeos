<template>
  <Drawer :open="!!pile" name="pile" @close="emit('close')">
    <template #title><span class="size-2.5 rounded-full" :class="PILE_TEXT[cur].dot" aria-hidden="true" />{{ PILE_TEXT[cur].title }} · {{ left }}</template>
    <template #sub>{{ blurb }} Change any one, or accept the lot.</template>
    <template #bar>
      <div class="flex flex-wrap items-center gap-2">
        <TabButtons v-if="switchable" :model-value="cur" :options="switchOptions" aria-label="Pile"
          data-pile-switch @update:model-value="(v) => emit('switch', v)" />
        <TabButtons v-if="sourceOptions.length > 2" v-model="source" :options="sourceOptions" aria-label="Source" data-pile-sources />
        <span class="ml-auto text-sm text-ink-gray-6 max-md:hidden">Tap a choice to settle one item now</span>
      </div>
    </template>
    <Skeleton v-if="!data" class="h-40 w-full" />
    <div v-else-if="!shown.length" class="py-6 text-sm text-ink-gray-6">Nothing in this pile.</div>
    <div v-for="row in shown" :key="row.ref" class="border-b border-outline-gray-1 py-3 last:border-b-0"
      :class="row.settled && '-mx-5 px-5 bg-surface-green-1'" data-pile-row :data-ref="row.ref" :data-settled="row.settled ? 1 : 0">
      <template v-if="row.settled">
        <div class="flex items-center gap-2">
          <span class="lucide-check size-4 text-ink-green-9" aria-hidden="true" />
          <span class="flex-1 text-base-medium text-ink-green-9">{{ row.pile !== cur ? `Moved to ${PILE_TEXT[row.pile].title}` : 'Settled' }}</span>
          <Button variant="ghost" label="Undo" data-pile-row-undo @click="emit('undo', row)" />
        </div>
        <div class="pl-6 text-sm text-ink-gray-7">{{ row.title }}</div>
      </template>
      <template v-else>
        <div class="flex items-start gap-2">
          <Badge size="sm" theme="gray" :label="row.source" />
          <span class="min-w-0 flex-1 text-base-medium text-ink-gray-9">
            <span v-if="row.sensitive" class="lucide-lock mr-1 inline-block size-3.5 text-ink-gray-6" role="img" aria-label="Sensitive" data-sensitive-lock />{{ row.title }}</span>
          <Button class="flex-none" variant="ghost" size="sm" icon="lucide-external-link" label="Open" @click="openRef(refOf(row.doctype, row.name))" />
        </div>
        <div class="mt-0.5 text-sm text-ink-gray-6">{{ row.area_name || 'No area' }} · {{ ageText(row) }} · <i>{{ row.reason }}</i></div>
        <div v-if="cur === 'needs'" class="mt-2 flex flex-wrap gap-2">
          <Button v-for="c in choicesFor(row)" :key="c.label" :label="c.label" :data-needs-choice="c.label" @click="emit('settle', row, c.decision, c.chase)" />
        </div>
        <div v-else class="mt-2 flex flex-wrap gap-2">
          <Button v-for="p in PILES" :key="p" :variant="p === row.pile ? 'solid' : 'subtle'" :label="SHORT[p]" :data-pile-choice="p"
            @click="emit('settle', row, p)" />
        </div>
      </template>
    </div>
    <template #footer>
      <span class="flex-1 text-sm text-ink-gray-6" data-pile-footer-line>{{ settled }} settled · {{ left }} left in this pile</span>
      <Button v-if="cur !== 'needs'" variant="solid" :label="`${pileText(cur, pkey, 'verb')} ${left}`" :disabled="!left" data-pile-accept @click="emit('accept', cur)" />
    </template>
  </Drawer>
</template>
<script setup>
// A pile opened (board 25): what happens to its items, source filters with counts, each item with its source, area, age and
// the assistant's reason. A choice on a row settles that item at once; the footer applies the pile's decision to the rest.
import { computed, ref, watch } from 'vue'
import { Badge, Button, Skeleton, TabButtons } from 'frappe-ui'
import Drawer from '@/components/ui/Drawer.vue'
import { ageText, choicesFor, PILE_TEXT, pileText } from '@/lib/review'
import { openRef, refOf } from '@/lib/pane'

const PILES = ['keep', 'park', 'letgo']
const SHORT = { keep: 'Keep', park: 'Park', letgo: 'Let go' }
const props = defineProps({ pile: String, pkey: String, data: Object, switchable: Boolean })
const emit = defineEmits(['close', 'settle', 'undo', 'accept', 'switch'])
const cur = computed(() => props.pile || 'keep')
const switchOptions = computed(() => [...(props.data?.needs || cur.value === 'needs' ? [{ label: 'Needs you', value: 'needs' }] : []),
  ...PILES.map((p) => ({ label: PILE_TEXT[p].title, value: p }))])
const source = ref('all')
watch(() => props.pile, () => (source.value = 'all'))
const rows = computed(() => props.data?.rows || [])
const shown = computed(() => rows.value.filter((r) => source.value === 'all' || r.source === source.value))
const left = computed(() => rows.value.filter((r) => !r.settled && r.pile === cur.value).length)
const settled = computed(() => rows.value.filter((r) => r.settled).length)
const sourceOptions = computed(() => {
  const counts = props.data?.sources || {}
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  return [{ label: `All ${total}`, value: 'all' }, ...Object.entries(counts).map(([k, n]) => ({ label: `${k} ${n}`, value: k }))]
})
const blurb = computed(() => ({ keep: 'These stay on your plate.', park: 'These move to Someday and come back for a look in 3 months.',
  letgo: props.pkey === 'inbox' ? 'These go to the trash, where they stay for 30 days.' : 'These are dropped, or marked answered when someone was asked.',
  needs: 'The assistant could not decide these. Settle each one.' }[cur.value]))
</script>
