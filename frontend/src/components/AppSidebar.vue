<template>
  <!-- The sidebar (issue 14): the logo (on a site with two or more spaces it opens the space picker; issue 46 removed the lens and the pinned areas), + Capture, then Today, Brain (with the
       Needs you count), Goals and Library, with Review between Goals and Library once it is earned; Settings and the user
       at the bottom. The whole bar collapses to an icon rail. -->
  <Sidebar :collapsible="true" :collapsed="nav.rail" width="232px" aria-label="Places" data-sidebar @update:collapsed="onCollapse">
    <SidebarHeader title="Life OS" :subtitle="manySpaces ? store.space : undefined" :menu-items="spaceMenu" data-space-picker>
      <template #prefix><span class="grid size-full place-items-center bg-surface-gray-10 text-sm font-semibold text-ink-base" aria-hidden="true">L</span></template>
    </SidebarHeader>
    <div class="px-2 pb-2 pt-1" :class="nav.rail && 'flex flex-col items-center'">
      <Button v-if="nav.rail" icon="lucide-plus" label="Capture" variant="solid" tooltip="Capture" data-nav-capture @click="store.captureOpen = true" />
      <Button v-else class="w-full" icon-left="lucide-plus" label="Capture" variant="solid" data-nav-capture @click="store.captureOpen = true" />
    </div>
    <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 pb-2" data-nav-groups>
      <nav class="flex flex-col gap-0.5" aria-label="Places" data-nav-places>
        <SidebarItem v-for="n in places" :key="n.to" :label="n.label" :icon="n.icon" :route="n.to" :active="activePlace === n.base" :data-nav-item="n.label"
          :aria-current="activePlace === n.base ? 'page' : undefined">
          <template v-if="countOf(n.label)" #suffix><CountBadge :c="countOf(n.label)" :name="n.label" /></template>
        </SidebarItem>
      </nav>
      <SetupCard v-if="!nav.rail && !store.isAgent" />
    </div>
    <div class="flex flex-col gap-0.5 border-t border-outline-gray-1 px-2 pb-3 pt-2" data-nav-bottom>
      <SidebarItem :label="SETTINGS.label" :icon="SETTINGS.icon" :route="SETTINGS.to" :active="activePlace === '/settings'" data-nav-item="Settings" />
      <!-- the user, with Help (the shortcuts and where things are) and Log out -->
      <div v-if="!nav.rail" class="flex items-center gap-1" data-nav-user>
        <Dropdown :options="userMenu">
          <Button class="!justify-start" variant="ghost" :label="firstName" data-nav-user-menu>
            <template #prefix><Avatar size="sm" :label="store.fullName || store.user" /></template>
          </Button>
        </Dropdown>
        <span class="flex-1" />
        <Button class="shrink-0" variant="ghost" label="Help" data-nav-help @click="emit('shortcuts')" />
      </div>
      <SidebarCollapseToggle />
    </div>
  </Sidebar>
</template>
<script setup>
import { computed, h } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Avatar, Badge, Button, Dropdown, Sidebar, SidebarCollapseToggle, SidebarHeader, SidebarItem } from 'frappe-ui'
import { PLACES, REVIEW, SETTINGS } from '@/lib/nav'
import { activePlace, nav, reviewShown, setRail } from '@/lib/sidebar'
import { manySpaces, setSpace } from '@/lib/lens'
import { store } from '@/lib/store'
import SetupCard from './SetupCard.vue'
import { navCount } from '@/lib/newMenu'

const emit = defineEmits(['logout', 'shortcuts'])
const router = useRouter()
// Review sits between Goals and Library once it is earned
const places = computed(() => (reviewShown.value ? [...PLACES.slice(0, 3), REVIEW, ...PLACES.slice(3)] : PLACES))
// the count the sidebar shows: Brain carries the Inbox's number (Needs you)
const countOf = (label) => (label === 'Brain' ? navCount(label) : null)
// the space picker: only on a site with two or more spaces
const spaceMenu = computed(() => (manySpaces.value ? [{ group: 'Space', options: store.spaces.map((s) => ({ label: s.name, selected: s.name === store.space,
  'data-space-item': s.name, onClick: () => setSpace(s.name) })) }] : []))
const firstName = computed(() => (store.fullName || store.user || '').split(' ')[0])
// a count is a door: it opens the list with exactly that many rows
const CountBadge = (p) => h(RouterLink, { class: 'relative mr-1.5 rounded-full focus-visible:focus-ring', to: p.c.to, 'aria-label': p.c.label, 'data-door': p.c.door,
  'data-nav-count': p.name, 'data-count-door': '', 'data-count-n': p.c.n, 'data-count-label': p.c.count.label, 'data-count-key': 'nav:' + p.name,
  onClick: (e) => e.stopPropagation() }, () => h(Badge, { label: p.c.n, theme: 'gray', variant: 'solid' }))
CountBadge.props = ['c', 'name']
// the rail is a desktop choice: the library collapses the sidebar by itself on a narrow window, which is not remembered
const onCollapse = (v) => { if (window.innerWidth >= 768) setRail(!!v) }
const userMenu = computed(() => [
  { label: 'Profile and appearance', icon: 'lucide-user', onClick: () => router.push({ path: '/settings', query: { tab: 'profile' } }) },
  { label: 'Keyboard shortcuts', icon: 'lucide-keyboard', onClick: () => emit('shortcuts') },
  { label: 'Log out', icon: 'lucide-log-out', onClick: () => emit('logout') },
])
</script>
