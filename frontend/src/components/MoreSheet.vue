<template>
  <!-- The phone's menu (issue 46 replaced the lens sheet): the spaces when the site has two or more, then Settings, the
       keyboard shortcuts and logging out, which the phone's tab bar has no tab for. -->
  <BottomSheet :open="open" title="Life OS" @update:open="(v) => emit('update:open', v)">
    <div class="flex max-h-[80dvh] flex-col gap-3 overflow-y-auto px-4 pb-6" data-more-sheet>
      <section v-if="manySpaces" class="flex flex-col gap-0.5" data-space-sheet>
        <div class="mb-1 text-sm-medium text-ink-gray-6">Space</div>
        <Button v-for="s in store.spaces" :key="s.name" class="!justify-start" size="lg" :variant="s.name === store.space ? 'subtle' : 'ghost'" :label="s.name"
          :aria-pressed="s.name === store.space" :data-space-item="s.name" @click="pick(s.name)">
          <template v-if="s.name === store.space" #suffix><span class="lucide-check ml-auto size-4 text-ink-gray-7" aria-hidden="true" /></template>
        </Button>
      </section>
      <SetupCard v-if="!store.isAgent" class="!mt-0" @go="emit('update:open', false)" />
      <section class="flex flex-col gap-0.5" :class="manySpaces && 'border-t border-outline-gray-1 pt-3'">
        <Button class="!justify-start" size="lg" variant="ghost" icon-left="lucide-settings" label="Settings" data-more-settings @click="go('/settings')" />
        <Button class="!justify-start" size="lg" variant="ghost" icon-left="lucide-keyboard" label="Keyboard shortcuts" @click="emit('update:open', false); emit('shortcuts')" />
        <Button class="!justify-start" size="lg" variant="ghost" icon-left="lucide-log-out" label="Log out" @click="emit('logout')" />
      </section>
    </div>
  </BottomSheet>
</template>
<script setup>
import { useRouter } from 'vue-router'
import { BottomSheet, Button } from 'frappe-ui'
import { manySpaces, setSpace } from '@/lib/lens'
import { store } from '@/lib/store'
import SetupCard from './SetupCard.vue'

defineProps({ open: Boolean })
const emit = defineEmits(['update:open', 'logout', 'shortcuts'])
const router = useRouter()
function pick(name) {
  emit('update:open', false)
  setSpace(name)
}
function go(path) {
  emit('update:open', false)
  router.push(path)
}
</script>
