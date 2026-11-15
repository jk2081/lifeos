<template>
  <div class="overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base" data-md-editor>
    <div class="flex flex-wrap items-center gap-0.5 border-b border-outline-gray-1 px-1.5 py-1" role="toolbar" aria-label="Formatting">
      <Button v-for="t in TOOLS" :key="t.key" variant="ghost" :icon="t.icon" :label="t.label" :tooltip="t.label" :data-tool="t.key" @mousedown.prevent @click="t.run()" />
    </div>
    <div ref="host"></div>
  </div>
</template>
<script setup>
// CodeMirror 6 in Markdown mode. Typing [[ opens a picker over the records a link can point to.
// Every colour of the editor is a token variable, so the light and the dark theme both work.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { EditorState } from '@codemirror/state'
import { EditorView, keymap, placeholder as placeholderExt, drawSelection } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { markdown } from '@codemirror/lang-markdown'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { autocompletion, completionKeymap, startCompletion } from '@codemirror/autocomplete'
import { tags as t } from '@lezer/highlight'
import { api } from '@/lib/api'

const props = defineProps({ modelValue: String, space: String, placeholder: { type: String, default: 'Write in Markdown. Type [[ to link a record.' } })
const emit = defineEmits(['update:modelValue'])
const host = ref(null)
let view = null

async function wikiSource(context) {
  const before = context.matchBefore(/\[\[[^\[\]\n]*$/)
  if (!before) return null
  const text = before.text.slice(2)
  let rows = []
  try {
    rows = await api('links.suggest', { space: props.space, text })
  } catch (e) {
    return null
  }
  return {
    from: before.from,
    filter: false,
    options: rows.map((r) => ({
      label: r.title, detail: r.kind + (r.ambiguous ? ' · same title, pick one' : ''),
      apply: (v, completion, from, to) => {
        // swallow a closing ]] that auto-pairing or the user already typed
        const after = v.state.sliceDoc(to, to + 2)
        v.dispatch({ changes: { from, to: after === ']]' ? to + 2 : to, insert: r.insert }, selection: { anchor: from + r.insert.length } })
      },
    })),
  }
}

// ---- the toolbar: each button edits the text the way typing the Markdown would ----
function wrap(mark) {
  if (!view) return
  const { from, to } = view.state.selection.main
  const inner = view.state.sliceDoc(from, to)
  view.dispatch({ changes: { from, to, insert: mark + inner + mark }, selection: { anchor: from + mark.length, head: from + mark.length + inner.length } })
  view.focus()
}
function prefix(make) {
  if (!view) return
  const { from, to } = view.state.selection.main
  const first = view.state.doc.lineAt(from).number
  const last = view.state.doc.lineAt(to).number
  const changes = []
  for (let n = first; n <= last; n++) changes.push({ from: view.state.doc.line(n).from, insert: make(n - first) })
  view.dispatch({ changes })
  view.focus()
}
function linkRecord() {
  if (!view) return
  const { from, to } = view.state.selection.main
  view.dispatch({ changes: { from, to, insert: '[[' }, selection: { anchor: from + 2 } })
  view.focus()
  startCompletion(view)
}
const TOOLS = [
  { key: 'bold', icon: 'lucide-bold', label: 'Bold', run: () => wrap('**') },
  { key: 'italic', icon: 'lucide-italic', label: 'Italic', run: () => wrap('*') },
  { key: 'heading', icon: 'lucide-heading', label: 'Heading', run: () => prefix(() => '## ') },
  { key: 'list', icon: 'lucide-list', label: 'List', run: () => prefix(() => '- ') },
  { key: 'numbered', icon: 'lucide-list-ordered', label: 'Numbered list', run: () => prefix((i) => `${i + 1}. `) },
  { key: 'quote', icon: 'lucide-text-quote', label: 'Quote', run: () => prefix(() => '> ') },
  { key: 'link', icon: 'lucide-brackets', label: 'Link a record', run: linkRecord },
]

const theme = EditorView.theme({
  '&': { fontSize: '15px', color: 'var(--ink-gray-8)', backgroundColor: 'var(--surface-base)' },
  '.cm-content': { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', lineHeight: '1.6', padding: '12px 0', caretColor: 'var(--ink-gray-9)' },
  '.cm-line': { padding: '0 14px' },
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': { minHeight: '320px' },
  '.cm-cursor': { borderLeftColor: 'var(--ink-gray-9)' },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': { backgroundColor: 'var(--surface-blue-2) !important' },
  '.cm-gutters': { backgroundColor: 'var(--surface-base)', color: 'var(--ink-gray-5)', borderRight: '1px solid var(--outline-gray-1)' },
  '.cm-activeLineGutter': { backgroundColor: 'var(--surface-gray-1)', color: 'var(--ink-gray-5)' },
  '.cm-tooltip': { backgroundColor: 'var(--surface-base)', border: '1px solid var(--outline-gray-2)', borderRadius: '8px', color: 'var(--ink-gray-8)', overflow: 'hidden' },
  '.cm-tooltip-autocomplete ul li': { padding: '4px 10px !important' },
  '.cm-tooltip-autocomplete ul li[aria-selected]': { backgroundColor: 'var(--surface-gray-2)', color: 'var(--ink-gray-9)' },
  '.cm-completionDetail': { color: 'var(--ink-gray-6)', fontStyle: 'normal', marginLeft: '8px' },
  '.cm-placeholder': { color: 'var(--ink-gray-6)' },
})
// Markdown marks, coloured from the tokens (CodeMirror's default style has fixed colours that only suit a light page).
const highlight = HighlightStyle.define([
  { tag: t.heading, fontWeight: '600', color: 'var(--ink-gray-9)' },
  { tag: t.strong, fontWeight: '600' },
  { tag: t.emphasis, fontStyle: 'italic' },
  { tag: t.strikethrough, textDecoration: 'line-through' },
  { tag: [t.link, t.url], color: 'var(--ink-blue-8)' },
  { tag: [t.monospace, t.literal], color: 'var(--ink-amber-9)' },
  { tag: t.quote, color: 'var(--ink-gray-6)' },
  { tag: [t.processingInstruction, t.meta, t.contentSeparator], color: 'var(--ink-gray-6)' },
])

onMounted(() => {
  view = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.modelValue || '',
      extensions: [
        history(), drawSelection(), EditorView.lineWrapping, markdown(), syntaxHighlighting(highlight, { fallback: true }),
        autocompletion({ override: [wikiSource], activateOnTyping: true, icons: false }),
        keymap.of([...completionKeymap, ...defaultKeymap, ...historyKeymap, indentWithTab]),
        placeholderExt(props.placeholder), theme,
        EditorView.updateListener.of((u) => { if (u.docChanged) emit('update:modelValue', u.state.doc.toString()) }),
      ],
    }),
  })
})
watch(() => props.modelValue, (v) => {
  if (view && v !== view.state.doc.toString()) view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: v || '' } })
})
onBeforeUnmount(() => view && view.destroy())
defineExpose({ focus: () => view && view.focus() })
</script>
