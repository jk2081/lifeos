<template>
  <section class="flex flex-col gap-3" data-source-rules>
    <Card class="flex flex-col gap-1" data-how-processed>
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <SectionHead>How this source is processed</SectionHead>
          <p class="text-sm text-ink-gray-6">Each capture goes down this list. The first rule that fits decides it, and costs nothing.</p>
        </div>
        <Button v-if="writable" icon-left="lucide-plus" label="Add a rule" data-add-rule @click="adding = true" />
      </div>
      <RuleList :rules="d?.rules || []" :writable="writable" :source="sourceKey" empty="No rules for this source yet. Change a guess twice and the Brain makes one." @changed="load" />
      <p class="border-t border-outline-gray-1 pt-3 text-sm text-ink-gray-7" data-brain-line>
        {{ d?.brain_line }} <RouterLink class="text-ink-blue-8 hover:underline" :to="`/brain/skills/${d?.skill || 'process-capture'}`" data-brain-skill>{{ d?.skill_title || 'process-capture' }}</RouterLink>
      </p>
    </Card>
    <Card class="flex flex-col gap-1" data-recently>
      <SectionHead>Recently</SectionHead>
      <Row v-for="x in d?.recently || []" :key="x.name" :pane="'inbox:' + x.name" :label="x.title" class="!flex-wrap !items-center justify-between gap-x-4 gap-y-1 text-sm" data-recent-row>
        <span class="min-w-0 flex-[1_1_240px] break-words text-ink-gray-9">{{ x.title }}</span>
        <span class="text-ink-gray-6" data-recent-decided>{{ x.decided }}</span>
      </Row>
      <EmptyState v-if="d && !d.recently.length" line="Nothing has come in from here yet. It will be listed here with what decided it." data-recent-empty />
    </Card>
    <RuleDialog v-model:open="adding" :source="sourceKey.startsWith('kind-') ? '' : sourceKey" @saved="load" />
  </section>
</template>
<script setup>
import EmptyState from '@/components/ui/EmptyState.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
// A source's Rules tab, the top half (issue 117): the rules that apply, in the order they are tried; then what the Brain does with the rest;
// then the last ten items and what decided each. The same rules as Settings > Brain > Rules: changing one changes it in both.
import { ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import RuleDialog from '@/components/brain/RuleDialog.vue'
import RuleList from '@/components/brain/RuleList.vue'
import { tryCall } from '@/lib/api'
import { brainData } from '@/data/brain'
import { store } from '@/lib/store'

const props = defineProps({ sourceKey: { type: String, required: true }, writable: Boolean })
const d = ref(null)
const adding = ref(false)
async function load() {
  const res = await tryCall(() => brainData.rules.for_source({ key: props.sourceKey, space: store.space }))
  if (res) d.value = res
}
watch(() => [props.sourceKey, store.space], load, { immediate: true })
</script>
