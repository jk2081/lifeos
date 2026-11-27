<template>
  <div class="flex flex-col gap-4" data-person-pane>
    <Card v-if="brief" data-person-brief><Md :text="brief" /></Card>
    <Card v-else-if="loaded"><Empty title="No brief yet." hint="The Brain writes one once there is enough about them." /></Card>
    <section v-if="owe.owe_me.length || owe.i_owe.length" class="flex flex-col gap-3" data-person-owed>
      <div v-if="owe.owe_me.length" data-person-owe-me>
        <SectionHead :count="owe.owe_me.length">What they owe you</SectionHead>
        <Card flush class="!px-4">
          <Row v-for="t in owe.owe_me" :key="t.name" :pane="'task:' + t.name" :label="t.title" class="!items-center" data-person-owe-row>
            <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ t.title }}</span><span v-if="t.check_by" class="flex-none text-sm text-ink-gray-6">by {{ short(t.check_by) }}</span>
          </Row>
        </Card>
      </div>
      <div v-if="owe.i_owe.length" data-person-i-owe>
        <SectionHead :count="owe.i_owe.length">What you owe them</SectionHead>
        <Card flush class="!px-4">
          <Row v-for="t in owe.i_owe" :key="t.name" :pane="'task:' + t.name" :label="t.title" class="!items-center" data-person-owe-row>
            <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ t.title }}</span><span v-if="t.due_date" class="flex-none text-sm text-ink-gray-6">due {{ short(t.due_date) }}</span>
          </Row>
        </Card>
      </div>
    </section>
    <section v-if="details.length" data-person-details>
      <SectionHead>Details</SectionHead>
      <Card><dl class="flex flex-col gap-1 text-base"><div v-for="x in details" :key="x[0]" class="flex gap-3"><dt class="w-24 flex-none text-sm text-ink-gray-6">{{ x[0] }}</dt><dd class="min-w-0 break-words text-ink-gray-9">{{ x[1] }}</dd></div></dl></Card>
    </section>
    <section v-if="people.length" data-person-people>
      <SectionHead>{{ company ? 'People' : 'Related people' }}</SectionHead>
      <Card flush class="!px-4">
        <Row v-for="p in people" :key="p.name" :pane="'person:' + p.name" :label="p.title" class="!items-center" data-person-row>
          <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ p.title }}</span>
          <span class="flex-none text-sm text-ink-gray-6">{{ p.role || p.why }}</span>
        </Row>
      </Card>
    </section>
    <section v-if="open.length">
      <SectionHead>Open</SectionHead>
      <Card flush class="!px-4">
        <Row v-for="t in open" :key="t.name" :pane="'task:' + t.name" :label="t.title" class="!items-center">
          <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ t.title }}</span>
        </Row>
      </Card>
    </section>
    <section v-if="mentions.length" data-person-mentions>
      <SectionHead>Mentions <span class="text-sm text-ink-gray-6">{{ total }}</span></SectionHead>
      <Card flush class="!px-4">
        <template v-for="e in mentions" :key="e.ref">
          <Row v-if="e.ref" :pane="e.ref" :label="e.title" class="!items-center" data-person-mention>
            <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ e.title }}</span><span class="flex-none text-sm text-ink-gray-6">{{ short(e.date) }}</span>
          </Row>
          <Row v-else class="!items-center" data-person-mention>
            <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ e.title }}</span><span class="flex-none text-sm text-ink-gray-6">{{ short(e.date) }}</span>
          </Row>
        </template>
      </Card>
    </section>
  </div>
</template>
<script setup>
// A person or company in the pane (issue 123): who they are, the Brain's brief and what is open with them. Open full page is their own page.
import { onMounted, ref } from 'vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import Md from '@/components/Md.vue'
import { tryCall } from '@/lib/api'
import { itemData } from '@/data/item'
import { short } from '@/lib/dates'

const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const brief = ref('')
const open = ref([])
const people = ref([])
const mentions = ref([])
const total = ref(0)
const company = ref(false)
const details = ref([])
const loaded = ref(false)
const owe = ref({ owe_me: [], i_owe: [] })
onMounted(async () => {
  const res = await tryCall(() => itemData.people.get({ name: props.name }))
  if (!res) return emit('missing')
  brief.value = res.brief || ''
  open.value = (res.open?.tasks || []).slice(0, 8)
  people.value = res.related || []
  company.value = res.kind === 'Organisation'
  mentions.value = (res.mentioned || []).slice(0, 12)
  total.value = res.mentioned_total || 0
  details.value = [['Role', res.role], ['Email', res.email], ['Phone', res.phone], ['Works at', res.organisation?.title || res.organisation?.full_name], ['Also called', (res.aliases || []).join(', ')]].filter((x) => x[1])
  loaded.value = true
  owe.value = (await tryCall(() => itemData.tasks.person_owed({ person: props.name }))) || owe.value
  emit('meta', { title: res.title, kind: company.value ? 'Company' : 'Person', sub: [res.role, res.path].filter(Boolean).join(' · '), fullPage: `/library/pages/Life Person/${props.name}` })
})
</script>
