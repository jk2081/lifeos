<template>
  <FrappeUIProvider>
    <div v-if="store.ready" class="app">
      <nav class="sb" aria-label="Sections">
        <Dropdown :options="spaceOptions">
          <button class="sp" type="button" aria-label="Switch space">
            <div class="lg">L</div>
            <span class="truncate">{{ store.space || 'No space' }}</span>
            <Ico style="margin-left: auto; color: var(--ink-gray-6)" :size="14" stroke="2" d="m6 9 6 6 6-6" />
          </button>
        </Dropdown>
        <div v-for="n in NAV" :key="n.to" class="nvw">
          <RouterLink :to="n.to" class="nv" :class="{ on: isOn(n) }"><Ico :d="n.d" />{{ n.label }}</RouterLink>
          <RouterLink v-if="n.label === 'Inbox' && store.counts.to_review" class="ct" :to="{ path: '/inbox', query: { status: 'To Review' } }"
            :aria-label="`${store.counts.to_review} to review`" data-door="nav-review">{{ store.counts.to_review }}</RouterLink>
        </div>
        <div style="flex: 1"></div>
        <button class="nv" type="button" style="border: 0; background: none; cursor: pointer; width: 100%; font-size: 14px"
          @click="store.searchOpen = true">
          <Ico :d="SEARCH_ICON" />Search<span class="ct">⌘K</span>
        </button>
        <RouterLink :to="SETTINGS.to" class="nv" :class="{ on: isOn(SETTINGS) }"><Ico :d="SETTINGS.d" />Settings</RouterLink>
      </nav>

      <main class="main">
        <RouterView v-slot="{ Component }">
          <component :is="Component" :key="store.space + ':' + route.path" />
        </RouterView>
      </main>

      <nav class="tabbar" aria-label="Sections">
        <RouterLink v-for="n in TABS" :key="n.to" :to="n.to" class="tab" :class="{ on: isOn(n) }">
          <Ico :d="n.d" :size="22" />{{ n.label }}
        </RouterLink>
        <button class="tab" type="button" :class="{ on: moreOpen }" @click="moreOpen = !moreOpen">
          <Ico :d="MORE_ICON" :size="22" />More
        </button>
      </nav>
      <button v-if="showFabNow" class="fab" type="button" aria-label="Add" @click="store.quickAdd = true">
        <Ico :d="PLUS_ICON" :size="24" stroke="2" />
      </button>

      <div v-if="moreOpen" class="more-sheet only-phone">
        <div class="sh" style="font-size: 12px">Space</div>
        <div class="chips" style="margin-bottom: 16px">
          <button v-for="s in store.spaces" :key="s.name" class="ch" :class="{ on: s.name === store.space }" type="button"
            @click="store.space = s.name">{{ s.name }}</button>
        </div>
        <RouterLink v-for="n in [...NAV, SETTINGS]" :key="n.to" :to="n.to" class="nv" :class="{ on: isOn(n) }" @click="moreOpen = false">
          <Ico :d="n.d" :size="20" />{{ n.label }}
        </RouterLink>
        <a class="nv" href="/api/method/logout" @click.prevent="logout"><Ico d="M10 5H5v14h5M14 8l4 4-4 4M18 12H9" :size="20" />Log out</a>
      </div>

      <RecordPane />
      <SearchPalette v-if="store.searchOpen" @close="store.searchOpen = false" />
      <QuickAdd v-if="store.quickAdd" @close="store.quickAdd = false" />
    </div>
    <div v-else-if="bootError" class="bd"><div class="cd">{{ bootError }} <a href="/login?redirect-to=/life">Log in</a></div></div>
  </FrappeUIProvider>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Dropdown, FrappeUIProvider, useColorScheme } from 'frappe-ui'
import Ico from './components/Ico.vue'
import SearchPalette from './components/SearchPalette.vue'
import RecordPane from './components/RecordPane.vue'
import QuickAdd from './components/QuickAdd.vue'
import { MORE_ICON, NAV, PLUS_ICON, SEARCH_ICON, SETTINGS } from './lib/nav'
import { boot, store } from './lib/store'
import { errorText } from './lib/api'

const route = useRoute()
const router = useRouter()
const moreOpen = ref(false)
const bootError = ref('')
const TABS = NAV.filter((n) => ['Today', 'Inbox', 'Tasks', 'Journal'].includes(n.label))

useColorScheme() // follows the system setting; stamps data-theme on <html>

const isOn = (n) => (n.to === '/' ? route.path === '/' : route.path === n.to || route.path.startsWith(n.to + '/'))
const showFab = computed(() => ['/', '/tasks', '/inbox'].includes(route.path) && !moreOpen.value)
const spaceOptions = computed(() => [
  { group: 'Spaces', items: store.spaces.map((s) => ({ label: s.name + (s.name === store.space ? '  ✓' : ''), onClick: () => (store.space = s.name) })) },
  { group: store.fullName || store.user, items: [
    { label: 'Settings', onClick: () => router.push('/settings') },
    { label: 'Log out', onClick: logout },
  ] },
])

async function logout() {
  await fetch('/api/method/logout', { method: 'POST', headers: { 'X-Frappe-CSRF-Token': window.csrf_token || '' } })
  window.location.href = '/login'
}

watch(() => route.fullPath, () => (moreOpen.value = false))
const showFabNow = computed(() => showFab.value && !route.query.open)

// Keyboard: Cmd/Ctrl+K search, n new task, g then a letter to jump, Esc closes panels.
let gAt = 0
function onKey(e) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    store.searchOpen = !store.searchOpen
    return
  }
  if (e.key === 'Escape') {
    // Esc closes the thing on top: search, quick add or the menu first, then the record pane
    if (store.searchOpen || store.quickAdd || moreOpen.value) {
      store.searchOpen = false
      store.quickAdd = false
      moreOpen.value = false
    } else window.dispatchEvent(new CustomEvent('lifeos-escape'))
    return
  }
  const el = e.target
  if (e.metaKey || e.ctrlKey || e.altKey || el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)) return
  if (el.closest && el.closest('.cm-editor')) return
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
