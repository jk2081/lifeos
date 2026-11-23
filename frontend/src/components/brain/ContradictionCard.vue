<template>
  <div class="flex flex-col gap-2 border-b border-outline-gray-1 py-3 last:border-b-0" :data-contradiction="finding.name">
    <div class="flex flex-wrap items-center gap-2">
      <Badge theme="orange" label="Pages disagree" />
      <span class="text-base-medium text-ink-gray-9" data-contradiction-question>{{ finding.question }}</span>
    </div>
    <div class="flex flex-col gap-2">
      <div v-for="(o, i) in finding.options" :key="i" class="flex flex-wrap items-center gap-2" :data-contradiction-option="i">
        <div class="min-w-0 flex-1 basis-64">
          <div class="break-words text-base text-ink-gray-9">“{{ o.fact }}”</div>
          <div class="text-sm text-ink-gray-6">{{ o.title }}<template v-if="o.source_title"> · from {{ o.source_title }}</template></div>
        </div>
        <Button v-if="canEdit" label="Keep this" :loading="busy === i" :disabled="busy !== null" :data-contradiction-keep="i" @click="keep(i)" />
      </div>
    </div>
  </div>
</template>
<script setup>
// A contradiction the weekly wiki check found (issue 54): two facts that cannot both be true. Keeping one rewrites the other page to say it
// and cites its source (context.decide).
import { ref } from 'vue'
import { Badge, Button, toast } from 'frappe-ui'
import { errorText } from '@/lib/api'
import { brainData } from '@/data/brain'

const props = defineProps({ finding: { type: Object, required: true }, canEdit: Boolean })
const emit = defineEmits(['changed'])
const busy = ref(null)
async function keep(i) {
  busy.value = i
  try {
    await brainData.context.decide({ finding: props.finding.name, choice: i })
    toast.success('Kept. The pages now agree.')
    emit('changed')
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.value = null
  }
}
</script>
