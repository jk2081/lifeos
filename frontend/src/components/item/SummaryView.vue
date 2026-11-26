<template>
  <div class="flex flex-col gap-4" data-summary>
    <template v-if="summary">
      <p class="text-base-medium text-ink-gray-9" data-summary-line>{{ summary.line }}</p>

      <section v-if="summary.to_act_on.length" class="flex flex-col gap-1.5" data-summary-group="act">
        <h3 class="text-sm-medium text-ink-gray-7">To act on · <span class="tabular-nums" data-group-count>{{ summary.to_act_on.length }}</span></h3>
        <Card flush>
          <div v-for="(l, i) in summary.to_act_on" :key="i" class="flex flex-wrap items-start gap-x-3 gap-y-1.5 border-b border-outline-gray-1 px-4 py-2.5 last:border-b-0" data-summary-line-row="act">
            <div class="min-w-0 flex-1 basis-60">
              <div class="break-words text-base text-ink-gray-9"><b v-if="l.who" class="font-semibold">{{ l.who }}</b> {{ l.what }}</div>
              <div class="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm text-ink-gray-6">
                <Badge :theme="WHERE[l.route]?.theme || 'gray'" :label="where(l)" data-line-where :data-where="l.route" />
                <SourceLink :source="l.source" @original="emit('original')" />
              </div>
            </div>
            <Dropdown v-if="writable" :options="menu(i, l)" placement="right">
              <Button size="sm" label="Change" data-line-change :aria-label="`Change where “${l.what}” goes`" />
            </Dropdown>
          </div>
        </Card>
      </section>

      <section v-if="summary.updates.length" class="flex flex-col gap-1.5" data-summary-group="updates">
        <h3 class="text-sm-medium text-ink-gray-7">Updates · <span class="tabular-nums" data-group-count>{{ summary.updates.length }}</span></h3>
        <Card flush>
          <div v-for="(u, i) in summary.updates" :key="i" class="flex flex-wrap items-baseline gap-x-3 border-b border-outline-gray-1 px-4 py-2.5 text-base text-ink-gray-9 last:border-b-0" data-summary-line-row="updates">
            <span class="min-w-0 flex-1 basis-60 break-words">{{ u.what }}</span>
            <SourceLink :source="u.source" @original="emit('original')" />
          </div>
        </Card>
      </section>

      <section v-if="summary.reports.length" class="flex flex-col gap-1.5" data-summary-group="reports">
        <h3 class="text-sm-medium text-ink-gray-7">Reports · <span class="tabular-nums" data-group-count>{{ summary.reports.length }}</span> <span class="font-normal text-ink-gray-6">filed, nothing to do</span></h3>
        <p class="break-words text-base text-ink-gray-8" data-summary-reports>
          <template v-for="(r, i) in summary.reports" :key="i"><span v-if="i" aria-hidden="true"> · </span><SourceLink :source="r.source" :label="r.title" plain @original="emit('original')" /></template>
        </p>
      </section>

      <section v-if="summary.facts.length" class="flex flex-col gap-1.5" data-summary-group="facts">
        <h3 class="text-sm-medium text-ink-gray-7">Key facts</h3>
        <ul class="flex list-disc flex-col gap-1 pl-5 text-base text-ink-gray-9"><li v-for="(f, i) in summary.facts" :key="i">{{ f }}</li></ul>
      </section>

      <p v-if="summary.sensitive" class="inline-flex items-center gap-1 text-sm text-ink-gray-6" data-summary-sensitive>
        <span class="lucide-lock size-3.5" aria-hidden="true" />{{ summary.sensitive === 1 ? '1 sensitive item' : `${summary.sensitive} sensitive items` }}</p>
      <Card v-if="!summary.to_act_on.length && !summary.updates.length && !summary.reports.length && !summary.facts.length && !summary.sensitive" data-summary-nothing>
        <Empty title="Nothing to act on." hint="The Brain read it and found nothing that asks anything of you." /></Card>
    </template>
    <Card v-else-if="item.summary_md" data-item-summary><Md :text="item.summary_md" /></Card>
    <Card v-else-if="item.status !== 'New' && item.status !== 'Processing'"><Empty title="No summary." hint="The Brain adds a summary when it reads the item." /></Card>
  </div>
  <Dialog v-model:open="askWho" title="Waiting on…" size="sm" data-waiting-dialog
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Move to the waiting pile', variant: 'solid', onClick: confirmWaiting }]">
    <FormControl v-model="who" label="Who is on it?" placeholder="Name of the person" data-waiting-who />
  </Dialog>
</template>
<script setup>
// The summary of an inbox item as data you can scan (issue 118): one line on top, then To act on (each line with its Change), Updates and
// Reports. A line that came from an email links to it. Older items, summarised as one paragraph, still show it.
import { computed, h, ref } from 'vue'
import { Badge, Button, Dialog, Dropdown, FormControl } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import Md from '@/components/Md.vue'
import { itemData } from '@/data/item'
import { tryCall } from '@/lib/api'
import { safeUrl } from '@/lib/editor/livePreview'

const props = defineProps({ item: { type: Object, required: true }, writable: Boolean })
const emit = defineEmits(['original', 'changed'])
const summary = computed(() => (props.item.summary ? { facts: [], ...props.item.summary } : null))
const WHERE = { plate: { label: 'Your plate', theme: 'blue' }, waiting: { label: 'Waiting', theme: 'amber' }, calendar: { label: 'Calendar', theme: 'green' }, not_needed: { label: 'Not needed', theme: 'gray' } }
const where = (l) => (l.route === 'waiting' && l.waiting_on ? `Waiting on ${l.waiting_on}` : WHERE[l.route]?.label || 'Waiting')

// a source that is a link opens it; a source such as "Email 3" opens the original tab
const SourceLink = {
  props: { source: String, label: String, plain: Boolean },
  emits: ['original'],
  setup(p, { emit: up }) {
    return () => {
      const url = /^https?:/i.test(p.source || '') ? safeUrl(p.source) : ''
      const text = p.label || (url ? (/mail\.google\.com/.test(url) ? 'Open in Gmail' : 'Open') : p.source || '')
      if (!text) return null
      const cls = 'text-ink-blue-8 hover:underline focus-visible:focus-ring'
      return url ? h('a', { href: url, target: '_blank', rel: 'noopener', class: cls, 'data-source-link': '' }, text)
        : h('button', { type: 'button', class: cls, 'data-source-link': '', onClick: () => up('original') }, text)
    }
  },
}

const askWho = ref(false)
const who = ref('')
let pending = null
function menu(i, l) {
  return [{ label: 'Your plate', icon: 'lucide-user', onClick: () => move(i, 'plate'), selected: l.route === 'plate' },
    { label: 'Waiting on…', icon: 'lucide-hourglass', onClick: () => { pending = i; who.value = l.waiting_on || ''; askWho.value = true } },
    { label: 'Add to calendar', icon: 'lucide-calendar-plus', onClick: () => move(i, 'calendar') },
    { label: 'Not needed', icon: 'lucide-x', onClick: () => move(i, 'not_needed') }]
}
async function move(index, to, waiting_on) {
  const res = await tryCall(() => itemData.inbox.change_line({ item: props.item.name, index, to, waiting_on }), 'Moved.')
  if (res) { props.item.summary = res.summary; emit('changed') }
  return res
}
async function confirmWaiting({ close }) {
  if (!who.value.trim()) return
  if (await move(pending, 'waiting', who.value.trim())) close()
}
</script>
