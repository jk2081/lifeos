<template>
  <Transition name="rpane">
    <aside v-if="cur" ref="el" class="rpane" :class="{ wide: cur.type === 'inbox' }" role="dialog" :aria-label="meta.title || label" tabindex="-1" :style="drag ? `transform: translateY(${drag}px); transition: none` : ''"
      data-pane :data-pane-ref="cur.ref">
      <header class="rp-hd" @touchstart.passive="tStart" @touchmove.passive="tMove" @touchend="tEnd">
        <div class="rp-grab" aria-hidden="true"></div>
        <div class="rp-top">
          <div style="min-width: 0; flex: 1">
            <div class="mt">{{ label }}</div>
            <h2 class="h1 rp-title" data-pane-title>{{ meta.title || (missing ? 'Not found' : 'Loading…') }}</h2>
          </div>
          <RouterLink v-if="meta.fullPage" class="bt s" :to="meta.fullPage" data-pane-full>Open full page</RouterLink>
          <button class="bt s ic" type="button" aria-label="Close" data-pane-close @click="closePane"><Ico d="M6 6l12 12M18 6L6 18" /></button>
        </div>
        <div v-if="meta.area || meta.project || meta.sub" class="chips">
          <RouterLink v-if="meta.area" class="ch sm" :to="`/areas/${meta.area}`">{{ meta.area_name || 'Area' }}</RouterLink>
          <a v-if="meta.project" class="ch sm" href="#" @click.prevent="openRef('project:' + meta.project)">Project: {{ meta.project_title || meta.project }}</a>
          <span v-if="meta.sub" class="mt">{{ meta.sub }}</span>
        </div>
      </header>
      <div class="rp-bd">
        <div v-if="meta.archived" class="cd rp-arch">
          <span>This record is archived. It is shown read-only.</span>
          <button v-if="meta.canRestore" class="bt s" type="button" data-restore @click="restore">Restore</button>
        </div>
        <div v-if="missing" class="cd"><Empty title="This record was not found." hint="It may be in another space, or it was removed." /></div>
        <component :is="VIEW[cur.type]" v-else :key="cur.ref + ':' + stamp" :name="cur.name" :type="cur.type" @meta="(m) => (meta = m)" @missing="missing = true"
          @changed="changed" @close="closePane" />
      </div>
    </aside>
  </Transition>
</template>

<script setup>
// One pane for every record type. Desktop: it slides in from the right and the list stays usable beside it.
// Phone: a sheet from the bottom that covers the screen, closed with its button or by swiping down on its header.
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Ico from './Ico.vue'
import Empty from './Empty.vue'
import TaskPane from './pane/TaskPane.vue'
import VaultPane from './pane/VaultPane.vue'
import ProjectPane from './pane/ProjectPane.vue'
import GoalPane from './pane/GoalPane.vue'
import PagePane from './pane/PagePane.vue'
import ChatPane from './pane/ChatPane.vue'
import EntryPane from './pane/EntryPane.vue'
import DayPane from './pane/DayPane.vue'
import NotePane from './pane/NotePane.vue'
import PlainPane from './pane/PlainPane.vue'
import { api, tryCall } from '@/lib/api'
import { TYPES, closePane, current as cur, openRef, paneNav, recordChanged } from '@/lib/pane'

const VIEW = { task: TaskPane, inbox: defineAsyncComponent(() => import('./ReviewBody.vue')), note: NotePane, vault: VaultPane, project: ProjectPane,
  goal: GoalPane, page: PagePane, chat: ChatPane, event: EntryPane, date: EntryPane, day: DayPane, checkin: PlainPane, month: PlainPane }
const router = useRouter()
const el = ref(null)
const meta = ref({})
const missing = ref(false)
const stamp = ref(0)
const drag = ref(0)
const label = computed(() => (cur.value ? TYPES[cur.value.type].label : ''))
let lastRef = ''
let opener = null
let startY = null

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
  if (await tryCall(() => api('archive.restore', { doctype: TYPES[cur.value.type].doctype, name: cur.value.name }), 'Restored.')) {
    stamp.value++
    changed()
  }
}
const otherDialog = () => [...document.querySelectorAll('[role="dialog"]')].some((d) => !d.hasAttribute('data-pane') && d.offsetParent !== null)
function step(n) {
  const i = paneNav.rows.indexOf(cur.value.ref)
  const next = paneNav.rows[i + n]
  if (i < 0 || !next) return
  router.replace({ query: { ...router.currentRoute.value.query, open: next, focus: undefined } })
}
function onKey(e) {
  if (!cur.value || e.metaKey || e.ctrlKey || e.altKey) return
  const t = e.target
  if (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || (t.closest && t.closest('.cm-editor'))) return
  if (otherDialog()) return
  if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); step(1) }
  else if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); step(-1) }
}
const onEsc = () => { if (cur.value && !otherDialog()) closePane() }

// swipe down on the header closes the sheet on a phone
function tStart(e) {
  startY = window.innerWidth <= 800 ? e.touches[0].clientY : null
}
function tMove(e) {
  if (startY !== null) drag.value = Math.max(0, e.touches[0].clientY - startY)
}
function tEnd() {
  const far = drag.value > 90
  drag.value = 0
  startY = null
  if (far) closePane()
}
onMounted(() => {
  window.addEventListener('keydown', onKey)
  window.addEventListener('lifeos-escape', onEsc)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('lifeos-escape', onEsc)
})
</script>
