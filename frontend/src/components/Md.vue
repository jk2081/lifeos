<template>
  <div class="md prose prose-sm max-w-none break-words text-ink-gray-8" :class="read && 'read'" @click="onClick" v-html="html"></div>
</template>
<script setup>
// Rendered Markdown. Raw HTML is off in the renderer and the result goes through DOMPurify. The type comes from the
// typography styles of the frappe-ui preset; `read` switches to the reading typeface with the line capped near 70 characters.
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import { renderMarkdown } from '@/lib/markdown'
import { openRoute } from '@/lib/pane'

const props = defineProps({ text: String, links: { type: Array, default: () => [] }, read: Boolean })
const sanitize = (html) => DOMPurify.sanitize(html, { ADD_ATTR: ['target'], FORBID_TAGS: ['style', 'form', 'input', 'iframe'] })
const html = computed(() => renderMarkdown(props.text, { links: props.links, sanitize }))

function onClick(e) {
  const a = e.target.closest('a')
  if (!a) return
  const href = a.getAttribute('href') || ''
  if (href.startsWith('/life')) {
    e.preventDefault()
    openRoute(href) // a [[link]] opens its record in the pane
  }
}
</script>
