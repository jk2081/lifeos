<template>
  <div class="flex flex-col gap-4" data-digest>
    <section v-for="(s, i) in sections" :key="i" :data-digest-section="s.title">
      <h3 v-if="s.title" class="mb-1.5 text-base-semibold text-ink-gray-9">{{ s.title }} <span class="text-sm font-normal text-ink-gray-6">{{ s.items.length || '' }}</span></h3>
      <Md v-if="s.intro" :text="s.intro" />
      <ul v-if="s.items.length" class="flex flex-col divide-y divide-outline-gray-1 rounded-5 border border-outline-gray-2">
        <li v-for="(it, j) in s.items" :key="j" class="flex flex-wrap items-start gap-2 px-3 py-2" data-digest-item>
          <Md class="min-w-0 flex-1 basis-[240px]" :text="it.text" />
          <Button v-for="(u, k) in it.gmail" :key="k" size="sm" icon-left="lucide-mail" label="Open in Gmail" data-open-gmail @click="open(u)" />
        </li>
      </ul>
    </section>
  </div>
</template>
<script setup>
// An email digest as headed lists: each section (Needs your attention, Waiting on others, Dates and deadlines, FYI from
// people, Company information, Left out) is a heading with its items, and each item's Gmail link is an "Open in Gmail" button.
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import Md from './Md.vue'

const props = defineProps({ text: { type: String, default: '' } })
const GMAIL = /\[([^\]]*)\]\((https:\/\/mail\.google\.com\/[^)\s]+)\)|(https:\/\/mail\.google\.com\/[^\s)]+)/g
function item(raw) {
  const gmail = []
  const text = raw.replace(GMAIL, (m, label, url, bare) => { gmail.push(url || bare); return label && !/^(open|gmail|link|open in gmail)$/i.test(label.trim()) ? label : '' })
    .replace(/\s*[·|–-]\s*$/, '').trim()
  return { text, gmail }
}
const sections = computed(() => {
  const out = []
  let cur = { title: '', intro: '', items: [] }
  let last = null
  for (const line of String(props.text || '').split('\n')) {
    const h = /^#{1,4}\s+(.*)$/.exec(line)
    if (h) {
      if (cur.title || cur.intro.trim() || cur.items.length) out.push(cur)
      cur = { title: h[1].trim(), intro: '', items: [] }
      last = null
      continue
    }
    const li = /^\s*(?:[-*+]|\d+[.)])\s+(.*)$/.exec(line)
    if (li && !/^\s{2,}/.test(line)) { last = li[1]; cur.items.push(last); continue }
    if (last !== null && line.trim()) { cur.items[cur.items.length - 1] += '\n' + line.trim(); continue }
    if (!cur.items.length) cur.intro += line + '\n'
  }
  if (cur.title || cur.intro.trim() || cur.items.length) out.push(cur)
  return out.map((s) => ({ ...s, items: s.items.map(item) }))
})
function open(u) { window.open(u, '_blank', 'noopener,noreferrer') }
</script>
