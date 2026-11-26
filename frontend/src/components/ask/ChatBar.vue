<template>
  <!-- phone: one chat bar above the tabs on every screen, with +, the camera and the mic. A message with no question is a capture. -->
  <div class="flex items-center gap-1 border-t border-outline-gray-1 bg-surface-base px-2 py-1.5" data-chat-bar>
    <AttachMenu size="lg" />
    <TextInput v-model="ask.draft" class="min-w-0 flex-1" placeholder="Ask, tell Life OS, or capture…" aria-label="Message Life OS" data-chat-bar-input @keydown.enter.prevent="go" />
    <MicButton size="lg" @text="(t) => (ask.draft = (ask.draft ? ask.draft + ' ' : '') + t)" />
    <Button v-if="ask.draft.trim() || ask.files.length" variant="solid" size="lg" icon="lucide-arrow-up" label="Send" data-chat-bar-send @click="go" />
    <Button v-else size="lg" variant="ghost" icon="lucide-message-square" label="Open chat" data-chat-bar-open @click="openChat()" />
  </div>
</template>
<script setup>
import { Button, TextInput } from 'frappe-ui'
import { ask, openChat, sendOrCapture } from '@/lib/ask'
import AttachMenu from './AttachMenu.vue'
import MicButton from './MicButton.vue'

const go = () => sendOrCapture(ask.draft)
</script>
