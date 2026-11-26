<template>
  <div class="flex basis-full flex-wrap items-center gap-2 rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5" role="group" aria-label="Change what the Brain did" data-change-menu>
    <template v-if="row.alt_area">
      <Button :disabled="busy" :label="row.area_name" :aria-label="`File in ${row.area_name}`" data-pick="first" @click="emit('decide', 'accept', row.area)" />
      <Button :disabled="busy" :label="row.alt_area_name" :aria-label="`File in ${row.alt_area_name}`" data-pick="second" @click="emit('decide', 'accept', row.alt_area)" />
    </template>
    <Pick v-if="row.takes_area" :model-value="null" :options="areaOptions()" placeholder="Another area or part" :clearable="false" data-change-area
      @update:model-value="(v) => v && emit('decide', 'accept', v)" />
    <Button :disabled="busy" label="Not needed" data-drop @click="emit('decide', 'reject')" />
    <Button :disabled="busy" label="Always ask about this sender" data-always-ask @click="emit('always-ask')" />
    <Button :disabled="busy" variant="ghost" label="Open it" data-open-capture @click="emit('open')" />
  </div>
</template>
<script setup>
// The one Change on a Needs you row (issue 117): the guess is taken as right, so the row has no Keep. Change opens this: another area or part,
// "Not needed" (the Brain makes a rule when you say it twice for the same sender), or "Always ask about this sender".
import { Button } from 'frappe-ui'
import Pick from '@/components/Pick.vue'
import { areaOptions } from '@/lib/lookups'

defineProps({ row: { type: Object, required: true }, busy: Boolean })
const emit = defineEmits(['decide', 'always-ask', 'open'])
</script>
