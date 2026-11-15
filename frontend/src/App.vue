<template>
  <FrappeUIProvider>
    <div v-if="store.ready" class="flex min-h-full bg-surface-base" data-app>
      <div class="sticky top-0 hidden h-screen shrink-0 border-r border-outline-gray-1 md:block">
        <Sidebar :collapsible="false" width="220px" aria-label="Sections">
          <SidebarHeader :title="store.space || 'No space'" :subtitle="store.fullName || store.user" :menu-items="spaceOptions" />
          <div class="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2 pt-1">
            <SidebarItem v-for="n in NAV" :key="n.to" :label="n.label" :icon="n.icon" :route="n.to" :active="isOn(n)">
              <template v-if="n.label === 'Inbox' && store.counts.to_review" #suffix>
                <RouterLink class="mr-1.5 rounded-full focus-visible:focus-ring" :to="{ path: '/inbox', query: { status: 'To Review' } }"
                  :aria-label="`${store.counts.to_review} to review`" data-door="nav-review"><Badge :label="store.counts.to_review" /></RouterLink>
              </template>
            </SidebarItem>
          </div>
          <div class="flex flex-col gap-0.5 px-2 pb-3 pt-1">
            <SidebarItem label="Search" icon="lucide-search" @click="store.searchOpen = true">
              <template #suffix><KeyboardShortcut class="mr-2" combo="Mod+K" /></template>
            </SidebarItem>
            <SidebarItem label="Shortcuts" icon="lucide-keyboard" @click="shortcutsOpen = true">
              <template #suffix><KeyboardShortcut class="mr-2" combo="Shift+Slash" /></template>
            </SidebarItem>
            <SidebarItem :label="SETTINGS.label" :icon="SETTINGS.icon" :route="SETTINGS.to" :active="isOn(SETTINGS)" />
          </div>
        </Sidebar>
      </div>

      <main class="flex min-w-0 flex-1 flex-col pb-[calc(72px+env(safe-area-inset-bottom))] md:pb-0" data-main>
        <RouterView v-slot="{ Component }">
          <component :is="Component" :key="store.space + ':' + route.path" />
        </RouterView>
      </main>

      <div class="fixed inset-x-0 bottom-0 z-30 md:hidden" data-tabbar>
        <MobileNav aria-label="Sections">
          <MobileNavItem v-for="n in TABS" :key="n.to" :label="n.label" :icon="n.icon" :route="n.to" :active="isOn(n) && !moreOpen" />
          <MobileNavItem label="More" icon="lucide-menu" :active="moreOpen" @click="moreOpen = !moreOpen" />
        </MobileNav>
      </div>
      <div v-if="showFab" class="fixed bottom-[calc(72px+env(safe-area-inset-bottom))] right-4 z-30 md:hidden">
        <Button class="!size-12 !rounded-full shadow-lg" variant="solid" size="lg" icon="lucide-plus" label="Add" @click="store.quickAdd = true" />
      </div>

      <BottomSheet v-model:open="moreOpen" title="Life OS">
        <div class="flex flex-col gap-4 px-4 pb-6">
          <div>
            <div class="mb-2 text-sm-medium text-ink-gray-6">Space</div>
            <TabButtons :model-value="store.space" :options="store.spaces.map((s) => ({ label: s.name, value: s.name }))" @update:model-value="(v) => (store.space = v)" />
          </div>
          <div class="flex flex-col gap-0.5">
            <Button v-for="n in [...NAV, SETTINGS]" :key="n.to" class="!justify-start" size="lg" :variant="isOn(n) ? 'subtle' : 'ghost'" :icon-left="n.icon" :label="n.label"
              :route="n.to" @click="moreOpen = false" />
            <Button class="!justify-start" size="lg" variant="ghost" icon-left="lucide-log-out" label="Log out" @click="logout" />
          </div>
        </div>
      </BottomSheet>

      <RecordPane />
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
import { Alert, Badge, BottomSheet, Button, FrappeUIProvider, KeyboardShortcut, KeyboardShortcutsDialog, LoadingIndicator, MobileNav, MobileNavItem,
  Sidebar, SidebarHeader, SidebarItem, TabButtons, useColorScheme } from 'frappe-ui'
import SearchPalette from './components/SearchPalette.vue'
import RecordPane from './components/RecordPane.vue'
import QuickAdd from './components/QuickAdd.vue'
import { NAV, SETTINGS } from './lib/nav'
import { boot, store } from './lib/store'
import { errorText } from './lib/api'
import { stepTab } from './lib/tabs'

const route = useRoute()
const router = useRouter()
const moreOpen = ref(false)
const shortcutsOpen = ref(false)
const bootError = ref('')
const TABS = NAV.filter((n) => ['Today', 'Inbox', 'Tasks', 'Journal'].includes(n.label))
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
const spaceOptions = computed(() => [
  { group: 'Spaces', options: store.spaces.map((s) => ({ label: s.name, selected: s.name === store.space, onClick: () => (store.space = s.name) })) },
  { group: store.fullName || store.user, options: [
    { label: 'Settings', icon: 'lucide-settings', onClick: () => router.push('/settings') },
    { label: 'Log out', icon: 'lucide-log-out', onClick: logout },
  ] },
])

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
    await boot()
  } catch (e) {
    bootError.value = errorText(e) || 'Could not load Life OS.'
  }
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>
