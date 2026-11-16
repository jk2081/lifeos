<template>
  <!-- Desktop: a slide-over on the right; the list stays usable beside it. -->
  <Transition v-if="!phone" enter-active-class="transition-transform duration-200 ease-out motion-reduce:transition-none" leave-active-class="transition-transform duration-200 ease-out motion-reduce:transition-none"
    enter-from-class="translate-x-full" leave-to-class="translate-x-full">
    <aside v-if="cur" ref="el" class="fixed inset-y-0 right-0 z-40 flex flex-col border-l border-outline-gray-2 bg-surface-base shadow-2xl outline-none"
      :class="cur.type === 'inbox' ? 'w-[min(760px,100vw)]' : 'w-[min(520px,100vw)]'" role="dialog" :aria-label="meta.title || label" tabindex="-1" data-pane :data-pane-ref="cur.ref">
      <PaneBody :cur="cur" :meta="meta" :label="label" :missing="missing" :stamp="stamp" @meta="(m) => (meta = m)" @missing="missing = true" @changed="changed" @restore="restore" />
    </aside>
  </Transition>
  <!-- Phone: frappe-ui's BottomSheet. Swipe down, tap outside or use the close button. -->
  <BottomSheet v-else :open="!!cur" @update:open="(v) => !v && closePane()">
    <div v-if="cur" ref="el" class="flex h-[82dvh] flex-col outline-none" role="group" :aria-label="meta.title || label" tabindex="-1" data-pane :data-pane-ref="cur.ref">
      <PaneBody :cur="cur" :meta="meta" :label="label" :missing="missing" :stamp="stamp" phone @meta="(m) => (meta = m)" @missing="missing = true" @changed="changed" @restore="restore" />
    </div>
  </BottomSheet>
</template>

<script setup>
// One pane for every record type. Desktop: our slide-over from the right (token colours, frappe-ui's dialog shadow),
// with the list still usable beside it. Phone: frappe-ui's BottomSheet. Which record is open lives in the URL (lib/pane.js).
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { BottomSheet } from 'frappe-ui'
import PaneBody from './pane/PaneBody.vue'
import { api, tryCall } from '@/lib/api'
import { TYPES, closePane, current as cur, paneNav, recordChanged } from '@/lib/pane'

const router = useRouter()
const phone = useMediaQuery('(max-width: 767px)')
const el = ref(null)
const meta = ref({})
const missing = ref(false)
const stamp = ref(0)
const label = computed(() => (cur.value ? meta.value?.kind || TYPES[cur.value.type].label : ''))
let lastRef = ''
let opener = null

watch(() => cur.value?.ref, async (now, before) => {
  meta.value = {}
  missing.value = false
  if (now && !before) opener = document.activeElement
  if (now) {
    lastRef = now
    await nextTick()
    el.value?.focus({ preventScroll: true })
    document.querySelector(`[data-ref="${CSS.escape(now)}"]`)?.scrollIntoView({ block: 'nearest' })
  } else {
    // focus goes back to the row the pane was opened from
    await nextTick()
    const row = lastRef && document.querySelector(`[data-ref="${CSS.escape(lastRef)}"]`)
    ;(row || (opener && document.contains(opener) ? opener : null))?.focus?.({ preventScroll: true })
  }
}, { immediate: true })

function changed() {
  if (cur.value) recordChanged(cur.value.ref)
}
async function restore() {
  if (await tryCall(() => api('archive.restore', { doctype: TYPES[cur.value.type].doctype || 'Life Inbox Item', name: cur.value.name }), 'Restored.')) {
    stamp.value++
    changed()
  }
}
const otherDialog = () => [...document.querySelectorAll('[role="dialog"]')].some((d) => !d.hasAttribute('data-pane') && d.offsetParent !== null)
function step(n) {
  const i = paneNav.rows.indexOf(cur.value.ref)
  const next = paneNav.rows[i + n]
  if (i < 0 || !next) return
  router.replace({ query: { ...router.currentRoute.value.query, open: next, focus: undefined, ptab: undefined } })
}
function onKey(e) {
  if (!cur.value || e.metaKey || e.ctrlKey || e.altKey) return
  const t = e.target
  if (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || (t.closest && t.closest('.cm-editor, [role="listbox"], [role="menu"], [role="combobox"], [role="tablist"], [role="radiogroup"]'))) return
  if (otherDialog()) return
  if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); step(1) }
  else if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); step(-1) }
}
const onEsc = () => { if (cur.value && !otherDialog()) closePane() }

onMounted(() => {
  window.addEventListener('keydown', onKey)
  window.addEventListener('lifeos-escape', onEsc)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('lifeos-escape', onEsc)
})
</script>
