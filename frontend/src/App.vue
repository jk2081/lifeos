<template>
  <FrappeUIProvider>
    <div v-if="store.ready" class="flex min-h-full bg-surface-base" data-app>
      <div class="sticky top-0 hidden h-screen shrink-0 border-r border-outline-gray-1 md:block">
        <AppSidebar @logout="logout" @shortcuts="shortcutsOpen = true" />
      </div>

      <main class="flex min-w-0 flex-1 flex-col pb-[calc(72px+env(safe-area-inset-bottom))] md:pb-0" data-main>
        <!-- phone: "Life OS" (the space too, on a site with two or more) at the top of every screen; tapping it opens the menu sheet -->
        <div class="sticky top-0 z-20 flex items-center border-b border-outline-gray-1 bg-surface-base px-2 py-1 md:hidden" data-more-bar>
          <Button class="min-w-0 !justify-start" variant="ghost" size="md" :label="manySpaces ? `Life OS · ${store.space}` : 'Life OS'" icon-right="lucide-chevron-down"
            aria-haspopup="dialog" data-more-title @click="moreOpen = true" />
        </div>
        <!-- issue 50: offline, only capture works; what was captured waits on the phone and is sent when the connection returns -->
        <div v-if="!online || queue.waiting" class="flex flex-wrap items-center gap-x-3 gap-y-0.5 border-b border-outline-gray-1 bg-surface-amber-2 px-4 py-1.5 text-sm text-ink-amber-9" role="status" data-offline-note>
          <span v-if="!online" data-offline>You are offline. Only capture works until the connection returns; other screens need one.</span>
          <span v-if="queue.waiting" data-queue-note>{{ queue.waiting }} waiting to send<template v-if="queue.failed"> ({{ queue.failed }} could not be sent)</template></span>
        </div>
        <RouterView v-slot="{ Component }">
          <ScreenBoundary><component :is="Component" :key="store.space + ':' + store.lensArea + ':' + route.path" /></ScreenBoundary>
        </RouterView>
      </main>

      <!-- phone (issue 14): Today and Brain, the round capture button, Goals and Library; Settings is in the menu sheet, Ask in every header -->
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
      <NewGoalDialog v-if="store.newKind === 'goal'" :model-value="true" area-required @saved="goalCreated" @habit="store.newKind = ''"
        @update:model-value="(v) => !v && (store.newKind = '')" />

      <NewRecord v-if="store.newKind === 'someday'" :model-value="true" title="Park on Someday" action="Park on Someday" :fields="somedayFields" :save="createSomeday"
        @update:model-value="(v) => !v && (store.newKind = '')" />
      <NewRecord v-if="store.newKind === 'date'" :model-value="true" title="Add important date" action="Add date" :fields="DATE_FIELDS" :initial="{ date: store.today, kind: 'Birthday' }"
        :save="createDate" @update:model-value="(v) => !v && (store.newKind = '')" />
      <OnboardingGuide v-if="onboarding.show" />
      <Button v-if="onboarding.show && onboarding.away" class="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 shadow-lg" variant="solid" label="Back to the guide" data-guide-return @click="onboarding.away = false" />
      <MoreSheet v-model:open="moreOpen" @logout="logout" @shortcuts="shortcutsOpen = true" />
      <ItemView />
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
import { todayData } from '@/data/today'
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
import { db } from './lib/api'
import { recordChanged } from './lib/pane'
import { areaOptions, loadLookups } from './lib/lookups'
import SearchPalette from './components/SearchPalette.vue'
import ItemView from '@/components/item/ItemView.vue'
import ScreenBoundary from './components/ScreenBoundary.vue'
import AskPanel from './components/ask/AskPanel.vue'
import QuickAdd from './components/QuickAdd.vue'
import CaptureSheet from './components/CaptureSheet.vue'
import { boot, store } from './lib/store'
import { initLens, manySpaces } from './lib/lens'
import MoreSheet from './components/MoreSheet.vue'
import OnboardingGuide from './components/OnboardingGuide.vue'
import { loadOnboarding, onboarding } from './lib/onboarding'
import { errorText } from './lib/api'
import { stepTab } from './lib/tabs'
import { clearOffline, queue, startQueue } from './lib/offline'

const route = useRoute()
const router = useRouter()
const moreOpen = ref(false)
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

// a new goal from the New menu: open-ended by default; a 12 Week Year goal is added on the grid
async function createNote(v) {
  const note = await db.insert({ doctype: 'Life Note', space: store.space, title: v.title, content_md: '' })
  store.newKind = ''
  router.push(`/library/${note.name}?edit=1`)
}
const somedayFields = computed(() => [{ name: 'title', label: 'What to park', required: true },
  { name: 'as_note', label: 'It is', options: [{ label: 'A task', value: 0 }, { label: 'A thought with no action (a note)', value: 1 }] }, { name: 'area', label: 'Area', options: areaOptions() },
  { name: 'body_md', label: 'More detail', type: 'textarea' }, { name: 'note', label: 'Why it can wait (optional)' }])
async function createSomeday(v) {
  await todayData.someday.create({ space: store.space, ...v })
  store.newKind = ''
  recordChanged('task:new')
  toast.success('Parked on the Someday list.')
}
// an important date from + Capture (issue 99): it repeats on this day every year
const DATE_FIELDS = [{ name: 'title', label: 'Name', required: true, placeholder: 'For example: Ruchi' },
  { name: 'kind', label: 'Kind', options: ['Birthday', 'Anniversary', 'Other'], required: true },
  { name: 'date', label: 'Date', type: 'date', required: true, help: 'It repeats on this day every year.' },
  { name: 'year', label: 'Year it first happened (optional)', type: 'number' }]
async function createDate(v) {
  const d = new Date(`${v.date}T00:00:00`)
  await todayData.calendar.add_important_date({ space: store.space, title: v.title, kind: v.kind, day: d.getDate(), month: d.getMonth() + 1, year: v.year || null })
  store.newKind = ''
  recordChanged('day')
  toast.success('Added. It shows on this day every year.')
}
function goalCreated(g) {
  store.newKind = ''
  router.push(`/goals/${g.name}`)
}
// the sidebar's areas come from the space's lookups, read again when the space changes or Settings changes them
watch(() => [store.ready, store.space], ([ready]) => ready && loadLookups(true), { immediate: true })

// issue 50: the phone's queue of captures is emptied before the session ends, so the next person to sign in sends none of it
const online = ref(navigator.onLine)
const setOnline = () => (online.value = navigator.onLine)
window.addEventListener('online', setOnline)
window.addEventListener('offline', setOnline)
async function logout() {
  await clearOffline()
  try {
    await fetch('/api/method/logout', { method: 'POST', headers: { 'X-Frappe-CSRF-Token': window.csrf_token || '' } })
  } finally {
    window.location.href = '/login'
  }
}

watch(() => route.fullPath, () => (moreOpen.value = false))

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
    if (!store.searchOpen && !store.quickAdd && !moreOpen.value && !shortcutsOpen.value) window.dispatchEvent(new CustomEvent('lifeos-escape'))
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
    startQueue() // issue 50: send what was captured offline, now and whenever the connection returns
    if (store.isAdmin && !store.isAgent) loadOnboarding() // the first-run guide (issue 49) and whether the site is still empty
  } catch (e) {
    bootError.value = errorText(e) || 'Could not load Life OS.'
  }
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>
