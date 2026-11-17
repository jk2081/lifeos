<template>
  <!-- The lens on a phone: the same entries as the sidebar's picker, as a bottom sheet. Settings and logging out are
       reached from here, since the phone's bar has no More tab (UX fixes, set 6). -->
  <BottomSheet :open="open" title="Focus" @update:open="(v) => emit('update:open', v)">
    <div class="flex max-h-[80dvh] flex-col gap-3 overflow-y-auto px-4 pb-6" data-lens-sheet>
      <section v-for="g in groups" :key="g.key" class="flex flex-col gap-0.5" :data-lens-group="g.key">
        <div v-if="g.label" class="mb-1 text-sm-medium text-ink-gray-6">{{ g.label }}</div>
        <Button v-for="e in g.entries" :key="e.key" class="!justify-start" size="lg" :variant="e.selected ? 'subtle' : 'ghost'" :label="e.label"
          :icon-left="e.icon" :aria-pressed="e.selected" :data-lens-item="e.key" @click="pick(e)">
          <template v-if="e.area || e.space" #prefix>
            <span v-if="e.area" class="size-2 shrink-0 rounded-full" :class="dotClass(e.area)" :style="e.depth ? { marginLeft: e.depth + 'rem' } : undefined" aria-hidden="true" />
            <span v-else class="grid size-5 place-items-center rounded-[5px] bg-surface-gray-3 text-xs font-medium text-ink-gray-7" aria-hidden="true">{{ e.space.charAt(0).toUpperCase() }}</span>
          </template>
          <template v-if="e.selected" #suffix><span class="lucide-check ml-auto size-4 text-ink-gray-7" aria-hidden="true" /></template>
        </Button>
      </section>
      <section class="flex flex-col gap-0.5 border-t border-outline-gray-1 pt-3">
        <Button class="!justify-start" size="lg" variant="ghost" icon-left="lucide-settings" label="Settings" data-lens-settings @click="go('/settings')" />
        <Button class="!justify-start" size="lg" variant="ghost" icon-left="lucide-keyboard" label="Keyboard shortcuts" @click="emit('update:open', false); emit('shortcuts')" />
        <Button class="!justify-start" size="lg" variant="ghost" icon-left="lucide-log-out" label="Log out" @click="emit('logout')" />
      </section>
    </div>
  </BottomSheet>
</template>
<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { BottomSheet, Button } from 'frappe-ui'
import { dotClass } from '@/lib/lens'
import { lensEntries } from './lensMenu'

defineProps({ open: Boolean })
const emit = defineEmits(['update:open', 'logout', 'shortcuts'])
const router = useRouter()
const groups = computed(() => [
  { key: 'space', label: 'Space', entries: lensEntries.value.filter((e) => e.group === 'Space') },
  { key: 'area', label: 'Area', entries: lensEntries.value.filter((e) => e.group === 'Area') },
  { key: 'more', label: '', entries: lensEntries.value.filter((e) => e.group === 'more') },
])
function pick(e) {
  emit('update:open', false)
  e.onClick()
}
function go(path) {
  emit('update:open', false)
  router.push(path)
}
</script>
