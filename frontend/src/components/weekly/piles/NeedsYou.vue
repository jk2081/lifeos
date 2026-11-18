<template>
  <!-- only what the assistant could not decide, one by one; a settled row collapses to one line with Undo, and the section
       folds away once all are settled -->
  <section v-if="rows.length && left" class="flex flex-col gap-1" data-needs-you>
    <h2 class="text-base-medium text-ink-gray-9">Needs you · {{ left }}</h2>
    <p class="text-sm text-ink-gray-6">The assistant could not decide these. Only these are one by one.</p>
    <Card flush class="mt-1">
      <div v-for="row in rows" :key="row.ref" class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-outline-gray-1 py-2.5 last:border-b-0"
        data-needs-row :data-ref="row.ref" :data-settled="row.settled ? 1 : 0">
        <template v-if="row.settled">
          <span class="lucide-check size-4 text-ink-green-9" aria-hidden="true" />
          <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-7">{{ settledText(row) }} · {{ row.title }}</span>
          <Button variant="ghost" size="sm" label="Undo" data-needs-undo @click="emit('undo', row)" />
        </template>
        <template v-else>
          <div class="min-w-0 flex-[1_1_280px]">
            <div class="flex items-center gap-1.5 text-base-medium text-ink-gray-9">
              <span v-if="row.sensitive" class="lucide-lock size-3.5 text-ink-gray-6" role="img" aria-label="Sensitive" data-sensitive-lock />{{ row.title }}</div>
            <div class="text-sm text-ink-gray-6">{{ row.source }} · {{ ageText(row) }}<template v-if="row.area_name"> · {{ row.area_name }}</template> · <i>{{ row.reason }}</i></div>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button v-for="c in choicesFor(row)" :key="c.label" :label="c.label" :data-needs-choice="c.label" @click="emit('settle', row, c.decision, c.chase)" />
          </div>
        </template>
      </div>
    </Card>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import { ageText, choicesFor, PILE_TEXT } from '@/lib/review'

const props = defineProps({ rows: Array })
const emit = defineEmits(['settle', 'undo'])
const left = computed(() => props.rows.filter((r) => !r.settled).length)
const settledText = (row) => (row.settled.chase ? 'Chase task made' : `Moved to ${PILE_TEXT[row.settled.decision].title}`)
</script>
