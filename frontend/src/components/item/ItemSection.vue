<template>
  <section class="flex flex-col gap-2" :data-item-section="name" :data-open="isOpen ? '' : undefined">
    <SectionHead class="!mb-0">
      <Button v-if="phone" variant="ghost" size="sm" class="-ml-2" :icon-left="isOpen ? 'lucide-chevron-down' : 'lucide-chevron-right'" :label="title"
        :aria-expanded="isOpen" :aria-controls="id" data-item-toggle @click="isOpen = !isOpen" />
      <template v-else>{{ title }}</template>
      <span v-if="count !== null && count !== undefined" class="tabular-nums text-ink-gray-6">{{ count }}</span>
      <template v-if="$slots.action" #action><slot name="action" /></template>
    </SectionHead>
    <div v-show="isOpen" :id="id" class="flex flex-col gap-3"><slot /></div>
  </section>
</template>
<script setup>
// One section of the item page (issue 10). On a phone its heading is a button that folds the section away; on wider
// screens every section is open and the heading is plain.
import { computed, ref, useId } from 'vue'
import { Button } from 'frappe-ui'
import SectionHead from '../ui/SectionHead.vue'

const props = defineProps({ name: String, title: String, count: { type: Number, default: null }, phone: Boolean, open: { type: Boolean, default: true } })
const id = useId()
const folded = ref(!props.open)
const isOpen = computed({ get: () => !props.phone || !folded.value, set: (v) => (folded.value = !v) })
</script>
