<template>
  <!-- desktop: one box, "Search or chat", with Cmd K; it opens the search palette, where Enter on a question chats -->
  <Button v-if="!phone" variant="outline" class="w-80 max-w-full !justify-start !font-normal !text-ink-gray-6" icon-left="lucide-search" label="Search or chat"
    aria-keyshortcuts="Meta+K Control+K" data-ask-box @click="store.searchOpen = true">
    <template #suffix><KeyboardShortcut class="ml-auto" combo="Mod+K" /></template>
  </Button>
  <!-- phone: a search icon and a Chat button on every screen -->
  <div v-else class="flex items-center gap-2" data-ask-phone>
    <Button size="lg" icon="lucide-search" label="Search" data-phone-search @click="store.searchOpen = true" />
    <Button size="lg" variant="solid" label="Chat" data-phone-ask @click="startAsk()" />
  </div>
</template>
<script setup>
import { useMediaQuery } from '@vueuse/core'
import { Button, KeyboardShortcut } from 'frappe-ui'
import { store } from '@/lib/store'
import { startAsk } from '@/lib/ask'
const phone = useMediaQuery('(max-width: 767px)')
</script>
