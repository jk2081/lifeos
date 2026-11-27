<template>
  <!-- One drawer on the right (issue 128). The page makes room for it from 1440 px; below that it floats over the page with a shadow; on a phone it is full screen. -->
  <Transition v-if="!phone" enter-active-class="transition-transform duration-200 ease-out motion-reduce:transition-none" leave-active-class="transition-transform duration-200 ease-out motion-reduce:transition-none"
    enter-from-class="translate-x-full" leave-to-class="translate-x-full">
    <aside v-if="open" class="flex h-screen min-w-0 flex-col border-l border-outline-gray-2 bg-surface-base"
      :class="docked ? 'sticky top-0 shrink-0' : 'fixed inset-y-0 right-0 z-40 max-w-full shadow-2xl'" :style="{ width: wide ? '50vw' : `min(${width}px, 100vw)` }"
      data-drawer-host :data-docked="docked ? 1 : 0" :data-wide="wide ? 1 : 0">
      <slot />
    </aside>
  </Transition>
  <div v-else-if="open" class="fixed inset-0 z-40 flex flex-col bg-surface-base pt-[env(safe-area-inset-top)]" data-drawer-host data-docked="0" data-wide="0">
    <slot />
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { WIDTH, drawer, isDocked as docked, isPhone as phone } from '@/lib/drawer'
const props = defineProps({ open: Boolean, width: { type: Number, default: WIDTH }, expanded: Boolean })
const wide = computed(() => !phone.value && (drawer.wide || props.expanded))
</script>
