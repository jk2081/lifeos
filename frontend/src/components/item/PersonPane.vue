<template>
  <div class="flex flex-col gap-4" data-person-pane>
    <Card v-if="brief" data-person-brief><Md :text="brief" /></Card>
    <Card v-else-if="loaded"><Empty title="No brief yet." hint="The Brain writes one once there is enough about them." /></Card>
    <section v-if="open.length">
      <SectionHead>Open</SectionHead>
      <Card flush class="!px-4">
        <Row v-for="t in open" :key="t.name" :pane="'task:' + t.name" :label="t.title" class="!items-center">
          <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ t.title }}</span>
        </Row>
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

const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const brief = ref('')
const open = ref([])
const loaded = ref(false)
onMounted(async () => {
  const res = await tryCall(() => itemData.pages.get({ doctype: 'Life Person', name: props.name }))
  if (!res) return emit('missing')
  const h = res.header
  brief.value = res.brief?.md || ''
  open.value = (res.open?.tasks || []).slice(0, 8)
  loaded.value = true
  emit('meta', { title: h.title, kind: h.kind_label, sub: [h.role, h.path].filter(Boolean).join(' · '), fullPage: `/library/pages/Life Person/${props.name}` })
})
</script>
