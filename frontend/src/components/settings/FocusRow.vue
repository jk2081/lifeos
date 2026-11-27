<template>
  <div class="flex min-h-7 items-center gap-2" :data-focus="f.name" :data-focus-name="f.area_name" :data-on="f.is_on ? 1 : 0">
    <Switch :model-value="!!f.is_on" :disabled="!isAdmin || busy" :aria-label="`${f.area_name} ${f.is_on ? 'on' : 'off'}`" :data-focus-switch="f.area_name" @update:model-value="(v) => emit('switch', v)" />
    <span class="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-0.5" :class="!f.is_on && 'opacity-60'">
      <Badge theme="blue" label="Focus" />
      <RefLink class="text-base text-ink-gray-9 hover:underline focus-visible:focus-ring" :to="`focus:${f.name}`">{{ f.area_name }}</RefLink>
      <span v-if="f.standard" class="text-sm text-ink-gray-6">{{ f.standard }}</span>
    </span>
    <Button v-if="isAdmin" size="sm" variant="ghost" class="!text-ink-blue-8" label="Edit" :aria-label="`Edit ${f.area_name}`" :data-edit-focus="f.name" @click="emit('edit')" />
  </div>
</template>
<script setup>
import RefLink from '@/components/ui/RefLink.vue'
import { Badge, Button, Switch } from 'frappe-ui'

defineProps({ f: { type: Object, required: true }, isAdmin: Boolean, busy: Boolean })
const emit = defineEmits(['switch', 'edit'])
</script>
