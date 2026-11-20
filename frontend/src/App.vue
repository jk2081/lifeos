<template>
  <FrappeUIProvider>
    <div v-if="store.ready" class="flex min-h-full bg-surface-base" data-app>
      <div class="sticky top-0 hidden h-screen shrink-0 border-r border-outline-gray-1 md:block">
        <AppSidebar @logout="logout" @shortcuts="shortcutsOpen = true" />
      </div>

      <main class="flex min-w-0 flex-1 flex-col pb-[calc(72px+env(safe-area-inset-bottom))] md:pb-0" data-main>
        <!-- phone: the lens is the title at the top of every screen; tapping it opens the picker as a sheet (UX fixes, set 6) -->
        <div class="sticky top-0 z-20 flex items-center border-b border-outline-gray-1 bg-surface-base px-2 py-1 md:hidden" data-lens-bar>
          <Button class="min-w-0 !justify-start" variant="ghost" size="md" :label="lensLabel" icon-right="lucide-chevron-down" aria-haspopup="dialog" data-lens-title
            @click="lensOpen = true">
            <template #prefix><span class="size-2 shrink-0 rounded-full" :class="lensArea ? dotClass(lensArea) : 'bg-surface-gray-5'" aria-hidden="true" /></template>
          </Button>
        </div>
        <RouterView v-slot="{ Component }">
          <ScreenBoundary><component :is="Component" :key="store.space + ':' + store.lensArea + ':' + route.path" /></ScreenBoundary>
        </RouterView>
      </main>

      <!-- phone (issue 14): Today and Brain, the round capture button, Goals and Library; Settings is in the lens sheet, Ask in every header -->
      <div class="fixed inset-x-0 bottom-0 z-30 md:hidden" data-tabbar>
        <MobileNav aria-label="Places">
          <template v-for="(n, i) in PLACES" :key="n.to">
            <div v-if="i === 2" class="flex items-center justify-center">
              <Button class="!size-12 -translate-y-1 !rounded-full shadow-lg" variant="solid" size="lg" icon="lucide-plus" label="Capture" data-tab-capture
                @click="store.captureOpen = true" />
            </div>
            <MobileNavItem :label="n.label" :icon="navCount(n.label) ? undefined : n.icon" :route="n.to" :active="activePlace === n.base" :data-tab-item="n.label">
              <!-- Brain carries the sidebar's count -->
              <span v-if="navCount(n.label)" class="relative inline-flex"><span :class="n.icon" class="size-5" aria-hidden="true" />
                <span class="absolute -right-3 -top-1.5" :data-tab-count="n.label"><Badge size="sm" theme="gray" variant="solid" :label="navCount(n.label).n" /></span></span>
            </MobileNavItem>
          </template>
        </MobileNav>
      </div>

      <NewRecord v-if="store.newKind === 'note'" :model-value="true" title="New note" action="Create note" :fields="[{ name: 'title', label: 'Title', required: true }]"
        :save="createNote" @update:model-value="(v) => !v && (store.newKind = '')" />
      <NewGoalDialog v-if="store.newKind === 'goal'" :model-value="true" :types="['Open', 'Annual']" area-required @saved="goalCreated" @habit="store.newKind = ''"
        @update:model-value="(v) => !v && (store.newKind = '')" />

      <NewRecord v-if="store.newKind === 'idea'" :model-value="true" title="New idea" action="Park on Someday" :fields="ideaFields" :save="createIdea"
        @update:model-value="(v) => !v && (store.newKind = '')" />
      <LensSheet v-model:open="lensOpen" @logout="logout" @shortcuts="shortcutsOpen = true" />
      <RecordPane />
      <AskPanel />
      <SearchPalette v-model:open="store.searchOpen" />
      <QuickAdd v-model:open="store.quickAdd" />
      <CaptureSheet v-model:open="store.captureOpen" />
      <KeyboardShortcutsDialog v-model:open="shortcutsOpen">
        <div class="grid gap-6 sm:grid-cols-3">
          <section v-for="g in SHORTCUTS" :key="g.title">
            <h3 class="mb-2 text-sm-medium text-ink-gray-6">{{ g.title }}</h3>
            <div v-for="s in g.shortcuts" :key="s.label" class="flex items-center justify-between gap-3 py-1 text-base text-ink-gray-8">
              <span>{{ s.label }}</span><KeyboardShortcut bg :combo="s.combo" :alt-combos="s.altCombos" />
            </div>
          </section>
        </div>
      </KeyboardShortcutsDialog>
    </div>
    <div v-else-if="bootError" class="p-6">
      <Alert theme="red" :title="bootError" :primary-action="{ label: 'Log in', href: '/login?redirect-to=/life' }" />
    </div>
    <div v-else class="grid h-full place-items-center"><LoadingIndicator class="size-5 text-ink-gray-5" /></div>
  </FrappeUIProvider>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Alert, Badge, Button, FrappeUIProvider, KeyboardShortcut, KeyboardShortcutsDialog, LoadingIndicator, MobileNav, MobileNavItem,
  toast, useColorScheme } from 'frappe-ui'
import AppSidebar from './components/AppSidebar.vue'
import NewRecord from './components/NewRecord.vue'
import NewGoalDialog from './components/goals/NewGoalDialog.vue'
import { GO, PLACES } from './lib/nav'
import { activePlace } from './lib/sidebar'
import { navCount } from './lib/newMenu'
import { api, db } from './lib/api'
import { recordChanged } from './lib/pane'
import { areaOptions, loadLookups } from './lib/lookups'
import SearchPalette from './components/SearchPalette.vue'
import RecordPane from './components/RecordPane.vue'
import ScreenBoundary from './components/ScreenBoundary.vue'
import AskPanel from './components/ask/AskPanel.vue'
import QuickAdd from './components/QuickAdd.vue'
import CaptureSheet from './components/CaptureSheet.vue'
import { boot, store } from './lib/store'
import { dotClass, initLens, lensArea, lensLabel } from './lib/lens'
import LensSheet from './components/lens/LensSheet.vue'
import { errorText } from './lib/api'
import { stepTab } from './lib/tabs'

const route = useRoute()
const router = useRouter()
const lensOpen = ref(false)
const shortcutsOpen = ref(false)
const bootError = ref('')
const SHORTCUTS = [
  { title: 'Anywhere', shortcuts: [
    { label: 'Search', combo: 'Mod+K', altCombos: ['Slash'] }, { label: 'New task', combo: 'N' }, { label: 'Close the pane or dialog', combo: 'Escape' },
    { label: 'Previous tab', combo: 'BracketLeft' }, { label: 'Next tab', combo: 'BracketRight' },
    { label: 'This list of shortcuts', combo: 'Shift+Slash' }] },
  { title: 'Go to: press G, then', shortcuts: GO.map((n) => ({ label: n.label, combo: n.key.toUpperCase() })) },
  { title: 'With a record open', shortcuts: [{ label: 'Next record in the list', combo: 'J', altCombos: ['ArrowDown'] },
    { label: 'Previous record in the list', combo: 'K', altCombos: ['ArrowUp'] }] },
]

useColorScheme() // light and dark come from frappe-ui: it follows the system setting and stamps data-theme on <html>

// a new goal from the New menu: open-ended by default (what a project was before set 6); a 12 Week Year goal is added on the grid
async function createNote(v) {
  const note = await db.insert({ doctype: 'Life Note', space: store.space, title: v.title, content_md: '' })
  store.newKind = ''
  router.push(`/library/${note.name}?edit=1`)
}
const ideaFields = computed(() => [{ name: 'title', label: 'Idea', required: true }, { name: 'area', label: 'Area', options: areaOptions() },
  { name: 'body_md', label: 'More detail', type: 'textarea' }, { name: 'note', label: 'Why it can wait (optional)' }])
async function createIdea(v) {
  await api('someday.create_idea', { space: store.space, ...v })
  store.newKind = ''
  recordChanged('idea:new')
  toast.success('Parked on the Someday list.')
}
function goalCreated(g) {
  store.newKind = ''
  router.push(`/goals/${g.name}`)
}
// the sidebar's areas come from the space's lookups, read again when the space changes or Settings changes them
watch(() => [store.ready, store.space], ([ready]) => ready && loadLookups(true), { immediate: true })

async function logout() {
  await fetch('/api/method/logout', { method: 'POST', headers: { 'X-Frappe-CSRF-Token': window.csrf_token || '' } })
  window.location.href = '/login'
}

watch(() => route.fullPath, () => (lensOpen.value = false))

// Keyboard: Cmd/Ctrl+K search, n new task, g then a letter to jump, ? the shortcut list, Esc closes panels.
// frappe-ui dialogs close themselves on Esc; the record pane listens for the event below.
let gAt = 0
function onKey(e) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    store.searchOpen = !store.searchOpen
    return
  }
  if (e.key === 'Escape') {
    if (!store.searchOpen && !store.quickAdd && !lensOpen.value && !shortcutsOpen.value) window.dispatchEvent(new CustomEvent('lifeos-escape'))
    return
  }
  const el = e.target
  if (e.metaKey || e.ctrlKey || e.altKey || el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)) return
  if (el.closest && el.closest('.cm-editor, [role="dialog"]:not([data-pane]), [role="listbox"], [role="menu"]')) return
  const key = e.key.toLowerCase()
  if (Date.now() - gAt < 1200) {
    gAt = 0
    const hit = GO.find((n) => n.key === key)
    if (hit) { e.preventDefault(); router.push(hit.to) }
    return
  }
  if (key === 'g') gAt = Date.now()
  else if (key === 'n') { e.preventDefault(); store.quickAdd = true }
  else if (key === '/') { e.preventDefault(); store.searchOpen = true }
  else if (e.key === '?') { e.preventDefault(); shortcutsOpen.value = true }
  else if (e.key === '[' || e.key === ']') { if (stepTab(e.key === '[' ? -1 : 1)) e.preventDefault() }
}

onMounted(async () => {
  window.addEventListener('keydown', onKey)
  try {
    await boot({ beforeReady: initLens })
  } catch (e) {
    bootError.value = errorText(e) || 'Could not load Life OS.'
  }
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>
