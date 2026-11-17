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
          <component :is="Component" :key="store.space + ':' + store.lensArea + ':' + route.path" />
        </RouterView>
      </main>

      <div class="fixed inset-x-0 bottom-0 z-30 md:hidden" data-tabbar>
        <MobileNav aria-label="Sections">
          <MobileNavItem v-for="n in TABS" :key="n.to" :label="n.label" :icon="navCount(n.label) ? undefined : n.icon" :route="n.to" :active="isOn(n) && !moreOpen" :data-tab-item="n.label">
            <!-- Inbox and Tasks carry the sidebar's counts -->
            <span v-if="navCount(n.label)" class="relative inline-flex"><span :class="n.icon" class="size-5" aria-hidden="true" />
              <span class="absolute -right-3 -top-1.5" :data-tab-count="n.label"><Badge size="sm" theme="red" :label="navCount(n.label).n" /></span></span>
          </MobileNavItem>
          <MobileNavItem label="More" icon="lucide-menu" :active="moreOpen" @click="moreOpen = !moreOpen" />
        </MobileNav>
      </div>
      <div v-if="showFab" class="fixed bottom-[calc(72px+env(safe-area-inset-bottom))] right-4 z-30 md:hidden">
        <Button class="!size-12 !rounded-full shadow-lg" variant="solid" size="lg" icon="lucide-plus" label="Add" @click="store.quickAdd = true" />
      </div>

      <!-- Phone: More is the sidebar's grouped list, full screen, with Search and New at the top -->
      <BottomSheet v-model:open="moreOpen" title="Life OS">
        <div class="flex h-[86dvh] flex-col gap-4 overflow-y-auto px-4 pb-6" data-more>
          <div class="flex gap-2">
            <Button class="flex-1" size="lg" icon-left="lucide-search" label="Search or ask" @click="moreOpen = false; store.searchOpen = true" />
            <Dropdown v-if="canWrite()" :options="newMenuItems().map((o) => ({ ...o, onClick: () => { moreOpen = false; o.onClick() } }))">
              <Button size="lg" variant="solid" icon-left="lucide-plus" label="New" data-more-new />
            </Dropdown>
          </div>
          <div>
            <div class="mb-2 text-sm-medium text-ink-gray-6">Space</div>
            <TabButtons :model-value="store.space" :options="store.spaces.map((s) => ({ label: s.name, value: s.name }))" @update:model-value="(v) => setLens({ space: v })" />
          </div>
          <section v-for="g in GROUPS" :key="g.key" class="flex flex-col gap-0.5" :data-more-group="g.key">
            <RouterLink v-if="g.key === 'areas'" to="/areas" class="mb-1 rounded-4 text-sm-medium text-ink-gray-6 hover:underline focus-visible:focus-ring" @click="moreOpen = false">Areas</RouterLink>
            <div v-else-if="g.label" class="mb-1 text-sm-medium text-ink-gray-6">{{ g.label }}</div>
            <template v-if="g.key === 'areas'">
              <template v-for="a in areaTree.slice(0, MAX_AREAS)" :key="a.name">
                <Button class="!justify-start" size="lg" :variant="activeKey === 'area:' + a.name ? 'subtle' : 'ghost'" icon-left="lucide-folder" :label="a.area_name" :route="`/areas/${a.name}`" />
                <Button v-for="c in a.children" :key="c.name" class="!justify-start pl-8" size="lg" :variant="activeKey === 'area:' + c.name ? 'subtle' : 'ghost'" icon-left="lucide-corner-down-right"
                  :label="c.area_name" :route="`/areas/${c.name}`" />
              </template>
              <Button v-if="areaTree.length > MAX_AREAS" class="!justify-start" size="lg" variant="ghost" icon-left="lucide-folders" label="All areas" route="/areas" />
            </template>
            <Button v-for="n in g.items" v-else :key="n.to" class="!justify-start" size="lg" :variant="activeKey === n.to ? 'subtle' : 'ghost'" :icon-left="n.icon" :label="n.label" :route="n.to">
              <template v-if="navCount(n.label)" #suffix><RouterLink class="rounded-full" :to="navCount(n.label).to" :aria-label="navCount(n.label).label" data-count-door
                :data-count-n="navCount(n.label).n" :data-count-label="navCount(n.label).count.label" :data-count-key="'more:' + n.label" @click.stop="moreOpen = false"><Badge :label="navCount(n.label).n" /></RouterLink></template>
            </Button>
          </section>
          <section class="flex flex-col gap-0.5 border-t border-outline-gray-1 pt-3">
            <Button v-for="n in BOTTOM" :key="n.to" class="!justify-start" size="lg" :variant="activeKey === n.to ? 'subtle' : 'ghost'" :icon-left="n.icon" :label="n.label" :route="n.to">
              <template v-if="navDot(n.label)" #suffix><span class="size-2 rounded-full bg-surface-amber-7" role="img" :aria-label="navDot(n.label).label" data-reset-dot /></template>
            </Button>
            <Button class="!justify-start" size="lg" variant="ghost" icon-left="lucide-log-out" label="Log out" @click="logout" />
          </section>
        </div>
      </BottomSheet>
      <NewRecord v-if="store.newKind === 'note'" :model-value="true" title="New note" action="Create note" :fields="[{ name: 'title', label: 'Title', required: true }]"
        :save="createNote" @update:model-value="(v) => !v && (store.newKind = '')" />
      <NewRecord v-if="store.newKind === 'project'" :model-value="true" title="New project" action="Add project" :fields="projectFields" :save="createProject"
        @update:model-value="(v) => !v && (store.newKind = '')" />

      <NewRecord v-if="store.newKind === 'idea'" :model-value="true" title="New idea" action="Park on Someday" :fields="ideaFields" :save="createIdea"
        @update:model-value="(v) => !v && (store.newKind = '')" />
      <LensSheet v-model:open="lensOpen" @logout="logout" @shortcuts="shortcutsOpen = true" />
      <RecordPane />
      <AskPanel />
      <SearchPalette v-model:open="store.searchOpen" />
      <QuickAdd v-model:open="store.quickAdd" />
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
import { Alert, Badge, BottomSheet, Button, Dropdown, FrappeUIProvider, KeyboardShortcut, KeyboardShortcutsDialog, LoadingIndicator, MobileNav, MobileNavItem,
  TabButtons, toast, useColorScheme } from 'frappe-ui'
import AppSidebar from './components/AppSidebar.vue'
import NewRecord from './components/NewRecord.vue'
import { BOTTOM, GROUPS } from './lib/nav'
import { MAX_AREAS, activeKey, areaTree } from './lib/sidebar'
import { navCount, navDot, newMenuItems } from './lib/newMenu'
import { api, db } from './lib/api'
import { recordChanged } from './lib/pane'
import { areaOptions, loadLookups } from './lib/lookups'
import SearchPalette from './components/SearchPalette.vue'
import RecordPane from './components/RecordPane.vue'
import AskPanel from './components/ask/AskPanel.vue'
import QuickAdd from './components/QuickAdd.vue'
import { NAV, SETTINGS } from './lib/nav'
import { boot, canWrite, store } from './lib/store'
import { dotClass, initLens, lensArea, lensLabel, setLens } from './lib/lens'
import LensSheet from './components/lens/LensSheet.vue'
import { errorText } from './lib/api'
import { stepTab } from './lib/tabs'

const route = useRoute()
const router = useRouter()
const moreOpen = ref(false)
const lensOpen = ref(false)
const shortcutsOpen = ref(false)
const bootError = ref('')
const TABS = NAV.filter((n) => ['Today', 'Inbox', 'Tasks', 'Journal'].includes(n.label))
// Graph is a view of Notes; its G shortcut stays
const SHORTCUTS = [
  { title: 'Anywhere', shortcuts: [
    { label: 'Search', combo: 'Mod+K', altCombos: ['Slash'] }, { label: 'New task', combo: 'N' }, { label: 'Close the pane or dialog', combo: 'Escape' },
    { label: 'Previous tab', combo: 'BracketLeft' }, { label: 'Next tab', combo: 'BracketRight' },
    { label: 'This list of shortcuts', combo: 'Shift+Slash' }] },
  { title: 'Go to: press G, then', shortcuts: [...NAV, SETTINGS].map((n) => ({ label: n.label, combo: n.key.toUpperCase() })) },
  { title: 'With a record open', shortcuts: [{ label: 'Next record in the list', combo: 'J', altCombos: ['ArrowDown'] },
    { label: 'Previous record in the list', combo: 'K', altCombos: ['ArrowUp'] }] },
]

useColorScheme() // light and dark come from frappe-ui: it follows the system setting and stamps data-theme on <html>

const isOn = (n) => (n.to === '/' ? route.path === '/' : route.path === n.to || route.path.startsWith(n.to + '/'))
const showFab = computed(() => ['/', '/tasks', '/inbox'].includes(route.path) && !moreOpen.value && !route.query.open)
const projectFields = computed(() => [{ name: 'title', label: 'Title', required: true }, { name: 'area', label: 'Area', required: true, options: areaOptions() },
  { name: 'outcome', label: 'Outcome', type: 'textarea', help: 'What will be true when this is done.' }, { name: 'target_date', label: 'Target date', type: 'date' }])
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
async function createProject(v) {
  const p = await db.insert({ doctype: 'Life Project', space: store.space, status: 'Active', ...v })
  store.newKind = ''
  await loadLookups(true)
  router.push(`/projects/${p.name}`)
}
// the sidebar's areas come from the space's lookups, read again when the space changes or Settings changes them
watch(() => [store.ready, store.space], ([ready]) => ready && loadLookups(true), { immediate: true })

async function logout() {
  await fetch('/api/method/logout', { method: 'POST', headers: { 'X-Frappe-CSRF-Token': window.csrf_token || '' } })
  window.location.href = '/login'
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
    const hit = [...NAV, SETTINGS].find((n) => n.key === key)
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
