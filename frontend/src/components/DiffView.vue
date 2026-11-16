<template>
  <div class="overflow-x-auto rounded-4 border border-outline-gray-2 font-mono text-sm" data-diff>
    <div v-if="!rows.length" class="px-3 py-2 text-ink-gray-6">No difference.</div>
    <div v-for="(r, i) in rows" :key="i" class="flex min-w-0 whitespace-pre-wrap break-words px-3 py-0.5"
      :class="r.kind === 'add' ? 'bg-surface-green-2 text-ink-green-9' : r.kind === 'del' ? 'bg-surface-red-2 text-ink-red-9' : r.kind === 'gap' ? 'bg-surface-gray-1 text-ink-gray-6' : 'text-ink-gray-8'"
      :data-diff-row="r.kind">
      <span class="w-5 flex-none select-none" aria-hidden="true">{{ r.kind === 'add' ? '+' : r.kind === 'del' ? '−' : '' }}</span>
      <span class="sr-only">{{ r.kind === 'add' ? 'Added: ' : r.kind === 'del' ? 'Removed: ' : '' }}</span>
      <span class="min-w-0 flex-1">{{ r.text || ' ' }}</span>
    </div>
  </div>
</template>
<script setup>
// A readable line diff of two Markdown texts: removed lines on red, added on green, unchanged lines around them,
// long unchanged stretches folded to "n lines unchanged". The diff is the `diff` package's diffLines.
import { computed } from 'vue'
import { diffLines } from 'diff'

const props = defineProps({ before: { type: String, default: '' }, after: { type: String, default: '' }, context: { type: Number, default: 2 } })
const rows = computed(() => {
  const out = []
  for (const part of diffLines(props.before || '', props.after || '')) {
    const lines = part.value.replace(/\n$/, '').split('\n')
    const kind = part.added ? 'add' : part.removed ? 'del' : 'same'
    for (const text of lines) out.push({ kind, text })
  }
  if (!out.some((r) => r.kind !== 'same')) return []
  // fold unchanged lines far from a change
  const near = out.map((_, i) => out.slice(Math.max(0, i - props.context), i + props.context + 1).some((r) => r.kind !== 'same'))
  const folded = []
  for (let i = 0; i < out.length; i++) {
    if (near[i] || out[i].kind !== 'same') { folded.push(out[i]); continue }
    let j = i
    while (j < out.length && !near[j] && out[j].kind === 'same') j++
    folded.push({ kind: 'gap', text: `${j - i} line${j - i === 1 ? '' : 's'} unchanged` })
    i = j - 1
  }
  return folded
})
</script>
