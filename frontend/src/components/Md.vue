<template>
  <div class="md" :class="{ read }" @click="onClick" v-html="html"></div>
</template>
<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import DOMPurify from 'dompurify'
import { renderMarkdown } from '@/lib/markdown'

const props = defineProps({ text: String, links: { type: Array, default: () => [] }, read: Boolean })
const router = useRouter()
const sanitize = (html) => DOMPurify.sanitize(html, { ADD_ATTR: ['target'], FORBID_TAGS: ['style', 'form', 'input', 'iframe'] })
const html = computed(() => renderMarkdown(props.text, { links: props.links, sanitize }))

function onClick(e) {
  const a = e.target.closest('a')
  if (!a) return
  const href = a.getAttribute('href') || ''
  if (href.startsWith('/life')) {
    e.preventDefault()
    router.push(href.replace(/^\/life/, '') || '/')
  }
}
</script>
