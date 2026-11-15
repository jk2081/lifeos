<template>
  <template v-if="d">
    <PageHead :title="d.page_number ? `Journal page ${d.page_number}` : 'Journal page'" :crumb="{ to: '/journal/pages', label: 'Pages', here: long(d.page_date, true) }" :sub="long(d.page_date, true)">
      <Button v-if="d.inbox_item" label="Open the inbox item" @click="openRef('inbox:' + d.inbox_item)" />
    </PageHead>
    <div class="page-body"><div class="cols">
      <div class="half"><section><SectionHead>Page</SectionHead>
        <div v-if="d.image" class="max-h-[80vh] overflow-auto rounded-5 border border-outline-gray-2 bg-surface-gray-1" :class="zoom ? 'cursor-zoom-out' : 'cursor-zoom-in'" @click="zoom = !zoom">
          <img class="block h-auto" :class="zoom ? 'w-[220%] max-w-none' : 'w-full'" :src="d.image" alt="Photographed journal page" /></div>
        <Card v-else><Empty title="No image." hint="This page has a transcript but no photograph." /></Card></section></div>
      <div class="half">
        <section><SectionHead>Transcript <template v-if="writable && !editing" #action><Button variant="ghost" size="sm" label="Edit" @click="start" /></template></SectionHead>
          <Card>
            <template v-if="editing"><Textarea v-model="draft" :rows="16" aria-label="Transcript" />
              <div class="mt-2 flex justify-end gap-2"><Button label="Cancel" @click="editing = false" />
                <Button variant="solid" label="Save transcript" @click="save" /></div></template>
            <Md v-else-if="d.transcript_md" :text="d.transcript_md" read />
            <Empty v-else title="No transcript." hint="Use Edit to type what the page says." />
          </Card></section>
        <section><SectionHead>Created from this page</SectionHead>
          <Card flush><Row v-for="c in d.created" :key="c.route" :pane="refOfRoute(c.route)" :label="c.title" :class="!refOfRoute(c.route) && 'cursor-pointer'" @click="!refOfRoute(c.route) && openRoute(c.route)">
            <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ c.title }}</div><div class="text-sm text-ink-gray-6">{{ c.kind }}</div></div></Row>
            <Empty v-if="!d.created.length" title="Nothing else was created from this page." hint="Tasks, ticks and check-ins accepted from the same photo are listed here." /></Card></section>
      </div>
    </div></div>
  </template>
  <div v-else-if="missing" class="page-body"><Card><Empty title="This page was not found." hint="It may belong to another space." /></Card></div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { Button, Textarea } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Md from '@/components/Md.vue'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { long } from '@/lib/dates'
import { openRef, openRoute, refOfRoute } from '@/lib/pane'

const props = defineProps({ id: String })
const d = ref(null)
const missing = ref(false)
const zoom = ref(false)
const editing = ref(false)
const draft = ref('')
const writable = computed(() => store.spaces.find((s) => s.name === d.value?.space)?.access === 'Write')
function start() {
  draft.value = d.value.transcript_md
  editing.value = true
}
async function save() {
  if (await tryCall(() => api('journal.save_page_transcript', { page: d.value.name, transcript_md: draft.value }), 'Transcript saved.')) {
    d.value.transcript_md = draft.value
    editing.value = false
  }
}
onMounted(async () => {
  try {
    d.value = await api('journal.page_detail', { page: props.id })
  } catch (e) {
    missing.value = true
  }
})
</script>
