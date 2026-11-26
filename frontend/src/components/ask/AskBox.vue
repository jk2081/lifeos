<template>
  <!-- desktop: one box, "Search or chat", with /; it opens the search palette, where Enter on a question chats. Cmd K opens the chat panel itself (issue 120) -->
  <Button v-if="!phone" variant="outline" class="w-80 max-w-full !justify-start !font-normal !text-ink-gray-6" icon-left="lucide-search" label="Search or chat"
    aria-keyshortcuts="/" data-ask-box @click="store.searchOpen = true">
    <template #suffix><KeyboardShortcut class="ml-auto" combo="Slash" /></template>
  </Button>
  <!-- phone: a search icon on every screen; the chat is the bar above the tabs -->
  <Button v-else size="lg" icon="lucide-search" label="Search" data-phone-search @click="store.searchOpen = true" />
</template>
<script setup>
import { useMediaQuery } from '@vueuse/core'
import { Button, KeyboardShortcut } from 'frappe-ui'
import { store } from '@/lib/store'
const phone = useMediaQuery('(max-width: 767px)')
</script>
