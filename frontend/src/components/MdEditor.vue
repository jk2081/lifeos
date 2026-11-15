<template>
  <div ref="host" class="mdeditor"></div>
</template>
<script setup>
// CodeMirror 6 in Markdown mode. Typing [[ opens a picker over the records a link can point to.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorState } from '@codemirror/state'
import { EditorView, keymap, placeholder as placeholderExt, drawSelection } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { markdown } from '@codemirror/lang-markdown'
import { syntaxHighlighting, defaultHighlightStyle } from '@codemirror/language'
import { autocompletion, completionKeymap } from '@codemirror/autocomplete'
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

const theme = EditorView.theme({
  '&': { fontSize: '15px', color: 'var(--ink-gray-9)', backgroundColor: 'var(--surface-base)' },
  '.cm-content': { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', lineHeight: '1.6', padding: '12px 0', caretColor: 'var(--ink-gray-9)' },
  '.cm-line': { padding: '0 14px' },
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': { minHeight: '320px' },
  '.cm-cursor': { borderLeftColor: 'var(--ink-gray-9)' },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': { backgroundColor: 'var(--surface-blue-2) !important' },
  '.cm-tooltip': { backgroundColor: 'var(--surface-base)', border: '1px solid var(--outline-gray-2)', borderRadius: '8px', color: 'var(--ink-gray-9)', overflow: 'hidden' },
  '.cm-tooltip-autocomplete ul li': { padding: '4px 10px !important' },
  '.cm-tooltip-autocomplete ul li[aria-selected]': { backgroundColor: 'var(--surface-gray-2)', color: 'var(--ink-gray-9)' },
  '.cm-completionDetail': { color: 'var(--ink-gray-6)', fontStyle: 'normal', marginLeft: '8px' },
  '.cm-placeholder': { color: 'var(--ink-gray-6)' },
})

onMounted(() => {
  view = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.modelValue || '',
      extensions: [
        history(), drawSelection(), EditorView.lineWrapping, markdown(), syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
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
<style scoped>
.mdeditor { border: 1px solid var(--outline-gray-2); border-radius: 10px; overflow: hidden; background: var(--surface-base); }
</style>
