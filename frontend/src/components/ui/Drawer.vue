<template>
  <DialogRoot :open="open" @update:open="(v) => !v && emit('close')">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-50 bg-black-overlay-200 dark:bg-black-overlay-700" />
      <DialogContent v-bind="sub || $slots.sub ? {} : { 'aria-describedby': undefined }"
        class="fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-surface-base shadow-2xl focus:outline-none md:w-[520px] md:border-l md:border-outline-gray-2"
        data-drawer :data-drawer-name="name">
        <div class="flex flex-none items-start gap-3 border-b border-outline-gray-1 px-5 pb-3 pt-4 max-md:pt-[calc(1rem+env(safe-area-inset-top))]">
          <div class="min-w-0 flex-1">
            <DialogTitle class="flex items-center gap-2 text-lg-semibold text-ink-gray-9"><slot name="title">{{ title }}</slot></DialogTitle>
            <DialogDescription v-if="sub || $slots.sub" class="mt-1 text-sm text-ink-gray-6"><slot name="sub">{{ sub }}</slot></DialogDescription>
          </div>
          <Button variant="ghost" icon="lucide-x" label="Close" :size="phone ? 'md' : 'sm'" data-drawer-close @click="emit('close')" />
        </div>
        <div v-if="$slots.bar" class="flex-none border-b border-outline-gray-1 px-5 py-2"><slot name="bar" /></div>
        <!-- only the list scrolls; the header and the footer stay put -->
        <div class="min-h-0 flex-1 overflow-y-auto px-5 py-3" data-drawer-body><slot /></div>
        <div v-if="$slots.footer" class="flex flex-none flex-wrap items-center gap-3 border-t border-outline-gray-1 bg-surface-base px-5 py-3 max-md:pb-[calc(0.75rem+env(safe-area-inset-bottom))]"
          data-drawer-footer><slot name="footer" /></div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
<script setup>
// The review's drawer (set 8): detail opens in a 520 px side sheet from the right over a dimmed page; on a phone it is a
// full-screen sheet. Built on reka-ui's Dialog parts, as frappe-ui's own BottomSheet is, so focus is trapped and returned,
// Esc closes it, and it is announced as a dialog. Header and footer stay put; only the body scrolls.
import { computed } from 'vue'
import { DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'
import { Button } from 'frappe-ui'
import { useMediaQuery } from '@vueuse/core'

defineProps({ open: Boolean, title: String, sub: String, name: String })
const emit = defineEmits(['close'])
const phone = computed(() => !wide.value)
const wide = useMediaQuery('(min-width: 768px)')
</script>
