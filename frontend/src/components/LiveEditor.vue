<template>
  <div class="lv-editor" :class="[raw && 'lv-raw', compact && 'lv-compact']" data-live-editor :data-raw="raw || undefined">
    <div v-if="!readonly" ref="bar" class="lv-toolbar flex items-center gap-0.5 overflow-x-auto" :class="floating && 'lv-floating'" :style="barStyle"
      role="toolbar" aria-label="Formatting" data-editor-toolbar>
      <Button v-for="t in TOOLS" :key="t.key" variant="ghost" :icon="t.icon" :label="t.label" :tooltip="t.tip" :data-tool="t.key"
        @mousedown.prevent @click="run(t)" />
      <FileUploader v-if="images" :doctype="doctype || undefined" :docname="docname || undefined" file-types="image/*" :private="true"
        @success="(f) => insertImage(f)" @failure="(e) => toast.error(errorText(e))">
        <template #default="{ openFileSelector, uploading }">
          <Button variant="ghost" icon="lucide-image" label="Image" tooltip="Image" data-tool="image" :loading="uploading" @mousedown.prevent @click="openFileSelector" />
        </template>
      </FileUploader>
    </div>
    <div ref="host" class="lv-host" :aria-label="label"></div>
  </div>
</template>
<script setup>
// The Markdown editor: one pane, formatted as you type (lib/editor/livePreview.js), on CodeMirror 6. No modes: click and type.
// "Show Markdown" (the `raw` prop) shows the plain text. Typing [[ opens a picker over the records a link can point to;
// / at the start of a line opens a menu of blocks. Pasted or dropped images upload as private files attached to the record.
// One typeface for writing and reading (the reading typeface), in a column of at most about 720 px.
import { libraryData } from '@/data/library'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Button, FileUploader, toast } from 'frappe-ui'
import { EditorState } from '@codemirror/state'
import { EditorView, keymap, placeholder as placeholderExt, drawSelection } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { markdown, markdownLanguage } from '@codemirror/lang-markdown'
import { indentUnit } from '@codemirror/language'
import { autocompletion, completionKeymap } from '@codemirror/autocomplete'
import { errorText } from '@/lib/api'
import { openRoute } from '@/lib/pane'
import { uploadFile } from '@/lib/upload'
import { livePreview, setLinks, setRaw } from '@/lib/editor/livePreview'
import * as cmd from '@/lib/editor/commands'

const props = defineProps({
  modelValue: String, space: String, links: { type: Array, default: () => [] },
  doctype: String, docname: String, // where pasted images are attached; with neither they are stored unattached (still private)
  raw: Boolean, readonly: Boolean, compact: Boolean, images: { type: Boolean, default: true },
  label: { type: String, default: 'Text' },
  placeholder: { type: String, default: 'Write here. Type [[ to link a record, / for blocks.' },
})
const emit = defineEmits(['update:modelValue', 'blur'])
const host = ref(null)
const bar = ref(null)
let view = null

async function wikiSource(context) {
  const before = context.matchBefore(/\[\[[^\[\]\n]*$/)
  if (!before) return null
  const text = before.text.slice(2)
  let rows = []
  try {
    rows = await libraryData.links.suggest({ space: props.space, text })
  } catch (e) {
    return null
  }
  return {
    from: before.from,
    filter: false,
    options: rows.map((r) => ({
      label: r.title, detail: r.kind + (r.ambiguous ? ' · same title, pick one' : ''),
      apply: (v, completion, from, to) => {
        const after = v.state.sliceDoc(to, to + 2) // swallow a closing ]] already typed
        v.dispatch({ changes: { from, to: after === ']]' ? to + 2 : to, insert: r.insert }, selection: { anchor: from + r.insert.length } })
      },
    })),
  }
}

const TOOLS = [
  { key: 'bold', icon: 'lucide-bold', label: 'Bold', tip: 'Bold (⌘B)', run: cmd.wrap('**') },
  { key: 'italic', icon: 'lucide-italic', label: 'Italic', tip: 'Italic (⌘I)', run: cmd.wrap('*') },
  { key: 'heading', icon: 'lucide-heading', label: 'Heading', tip: 'Heading', run: cmd.heading(2) },
  { key: 'list', icon: 'lucide-list', label: 'Bulleted list', tip: 'Bulleted list (⌘⇧8)', run: cmd.list('bullet') },
  { key: 'numbered', icon: 'lucide-list-ordered', label: 'Numbered list', tip: 'Numbered list (⌘⇧7)', run: cmd.list('ordered') },
  { key: 'checklist', icon: 'lucide-list-checks', label: 'Checklist', tip: 'Checklist', run: cmd.list('task') },
  { key: 'link', icon: 'lucide-link', label: 'Link', tip: 'Link (⌘K)', run: cmd.link },
  { key: 'wiki', icon: 'lucide-brackets', label: 'Link a record', tip: 'Link a record ([[)', run: cmd.wikiLink },
]

function run(t) { if (view) t.run(view) }

// ---- images: paste, drop or the toolbar ----
function insertImage(file, at) {
  if (!view || !file?.file_url) return
  const pos = at ?? view.state.selection.main.head
  const line = view.state.doc.lineAt(pos)
  const lead = line.text.trim() && pos !== line.from ? '\n' : ''
  const alt = (file.file_name || 'image').replace(/\.[^.]+$/, '').replace(/[\[\]]/g, '')
  cmd.insertAt(view, pos, `${lead}![${alt}](${file.file_url})\n`)
  view.focus()
}
async function uploadImages(files, at) {
  for (const f of files) {
    if (!f.type.startsWith('image/')) continue
    try {
      const doc = await uploadFile(f, props.doctype || undefined, props.docname || undefined)
      insertImage(doc, at)
    } catch (e) {
      toast.error(errorText(e))
    }
  }
}
const imageEvents = EditorView.domEventHandlers({
  paste(e) {
    const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith('image/'))
    if (!files.length || !props.images) return false
    e.preventDefault()
    uploadImages(files)
    return true
  },
  drop(e, v) {
    const files = [...(e.dataTransfer?.files || [])].filter((f) => f.type.startsWith('image/'))
    if (!files.length || !props.images) return false
    e.preventDefault()
    const pos = v.posAtCoords({ x: e.clientX, y: e.clientY }) ?? v.state.selection.main.head
    uploadImages(files, pos)
    return true
  },
})

function follow(href) {
  if (/^https?:|^mailto:/i.test(href)) window.open(href, '_blank', 'noopener,noreferrer')
  else openRoute(href)
}

// ---- on a phone the toolbar sits above the keyboard while the editor has focus ----
const focused = ref(false)
const kb = ref(0)
const phone = ref(window.innerWidth < 768)
const floating = computed(() => phone.value && focused.value && !props.readonly)
const barStyle = computed(() => (floating.value ? { bottom: kb.value + 'px' } : undefined))
function measure() {
  phone.value = window.innerWidth < 768
  const vv = window.visualViewport
  kb.value = vv ? Math.max(0, window.innerHeight - vv.height - vv.offsetTop) : 0
}

onMounted(() => {
  view = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.modelValue || '',
      extensions: [
        history(), drawSelection(), EditorView.lineWrapping, indentUnit.of('    '),
        markdown({ base: markdownLanguage }),
        livePreview({ onOpen: follow }),
        autocompletion({ override: [wikiSource, cmd.slashSource], activateOnTyping: true, icons: false }),
        keymap.of([
          { key: 'Mod-b', run: cmd.wrap('**') }, { key: 'Mod-i', run: cmd.wrap('*') }, { key: 'Mod-k', run: cmd.link },
          { key: 'Mod-Shift-7', run: cmd.list('ordered') }, { key: 'Mod-Shift-8', run: cmd.list('bullet') },
          ...completionKeymap,
          { key: 'Tab', run: cmd.indent, shift: cmd.outdent },
          ...defaultKeymap, ...historyKeymap,
        ]),
        placeholderExt(props.placeholder), imageEvents,
        EditorState.readOnly.of(props.readonly),
        EditorView.contentAttributes.of({ 'aria-label': props.label, 'aria-multiline': 'true' }),
        EditorView.updateListener.of((u) => {
          if (u.docChanged) emit('update:modelValue', u.state.doc.toString())
          if (u.focusChanged) {
            focused.value = u.view.hasFocus
            if (!u.view.hasFocus) emit('blur')
            measure()
          }
        }),
      ],
    }),
  })
  view.dispatch({ effects: [setLinks.of(props.links), setRaw.of(props.raw)] })
  window.visualViewport?.addEventListener('resize', measure)
  window.visualViewport?.addEventListener('scroll', measure)
  window.addEventListener('resize', measure)
})
watch(() => props.modelValue, (v) => {
  if (view && (v || '') !== view.state.doc.toString()) view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: v || '' } })
})
watch(() => props.links, (v) => view && view.dispatch({ effects: setLinks.of(v) }))
watch(() => props.raw, (v) => view && view.dispatch({ effects: setRaw.of(v) }))
onBeforeUnmount(() => {
  window.visualViewport?.removeEventListener('resize', measure)
  window.visualViewport?.removeEventListener('scroll', measure)
  window.removeEventListener('resize', measure)
  view && view.destroy()
})
defineExpose({ focus: () => view && view.focus(), view: () => view })
</script>
