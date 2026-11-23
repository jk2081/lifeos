<template>
  <Card class="flex flex-col gap-2" :data-batch="batch.key">
    <div class="flex items-baseline gap-2.5">
      <span class="text-2xl-semibold tabular-nums text-ink-gray-9" data-batch-count>{{ batch.count }}</span>
      <span class="text-lg-semibold text-ink-gray-9">{{ batch.title }}</span>
      <Badge v-if="batch.source === 'AI'" theme="violet" :label="batch.by ? 'Suggested by ' + batch.by : 'AI'" />
    </div>
    <p class="text-base text-ink-gray-7">Why: {{ batch.reason }}</p>
    <ul class="flex flex-col gap-1 text-base text-ink-gray-8" data-batch-samples>
      <li v-for="s in batch.samples" :key="s" class="break-words">· {{ s }}</li>
      <li v-if="batch.count > batch.samples.length" class="text-ink-gray-6">· …and {{ batch.count - batch.samples.length }} more</li>
    </ul>
    <div v-if="writable" class="mt-1 flex flex-wrap items-center gap-2" :class="phone && 'flex-col !items-stretch'">
      <Button :size="phone ? 'lg' : 'md'" :variant="batch.action === 'accept_notes' ? 'subtle' : 'solid'" :theme="batch.action === 'delete' ? 'red' : 'gray'"
        :label="batch.action_label" :loading="busy" data-batch-apply @click="$emit('apply', batch)" />
      <Button :size="phone ? 'lg' : 'md'" label="Review one by one" data-batch-review @click="$emit('review', batch)" />
      <Button v-if="!phone" variant="ghost" label="Skip" data-batch-skip @click="$emit('skip', batch)" />
    </div>
  </Card>
</template>
<script setup>
// One suggested batch on Reset: its count, the reason, three samples, the primary action, Review one by one and Skip.
import { Badge, Button } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
defineProps({ batch: Object, writable: Boolean, busy: Boolean, phone: Boolean })
defineEmits(['apply', 'review', 'skip'])
</script>
