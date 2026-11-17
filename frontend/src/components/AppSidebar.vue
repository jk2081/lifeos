<template>
  <!-- The sidebar (UX fixes, set 6): the lens at the top, + New, the four places (Plan opens to its tabs), the pinned areas as
       one-click lenses, and Settings and the user with Help at the bottom. The whole bar collapses to an icon rail. -->
  <Sidebar :collapsible="true" :collapsed="nav.rail" width="232px" aria-label="Places" data-sidebar @update:collapsed="onCollapse">
    <!-- the lens: the space and area every place narrows to -->
    <SidebarHeader :title="store.space || 'No space'" :subtitle="lensAreaName" :menu-items="lensMenu" data-lens-picker />
    <div class="px-2 pb-1 pt-1" :class="nav.rail && 'flex flex-col items-center'">
      <Dropdown v-if="canWrite()" :options="newMenu">
        <Button v-if="nav.rail" icon="lucide-plus" label="New" variant="solid" tooltip="New" data-nav-new />
        <Button v-else class="w-full" icon-left="lucide-plus" label="New" variant="solid" data-nav-new />
      </Dropdown>
    </div>
    <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 pb-2" data-nav-groups>
      <nav class="flex flex-col gap-0.5" aria-label="Places" data-nav-places>
        <template v-for="n in PLACES" :key="n.to">
          <SidebarItem :label="n.label" :icon="n.icon" :route="n.to" :active="activePlace === (n.base || n.to)" :data-nav-item="n.label"
            :aria-current="activePlace === (n.base || n.to) ? 'page' : undefined">
            <template v-if="countOf(n.label)" #suffix><CountBadge :c="countOf(n.label)" :name="n.label" /></template>
            <template v-else-if="n.base && !nav.rail" #suffix>
              <Button class="relative mr-0.5 !size-5" variant="ghost" :icon="planShown ? 'lucide-chevron-down' : 'lucide-chevron-right'"
                :label="planShown ? 'Hide the tabs of Plan' : 'Show the tabs of Plan'" :aria-expanded="planShown" data-nav-toggle="plan"
                @click.stop.prevent="setPlanOpen(!planShown)" />
            </template>
          </SidebarItem>
          <!-- Plan's tabs: the rhythms, a gap, then the lists -->
          <div v-if="n.base && planShown && !nav.rail" class="flex flex-col gap-0.5 pl-4" role="group" aria-label="Plan" data-nav-group="plan">
            <template v-for="(t, i) in PLAN_TABS" :key="t.value">
              <div v-if="i && t.group !== PLAN_TABS[i - 1].group" class="mx-2 my-1 border-t border-outline-gray-1" aria-hidden="true" />
              <SidebarItem :label="t.label" :route="planPath(t.value)" :active="activePlanTab === t.value" :data-nav-plan="t.value">
                <template v-if="countOf(SUB[t.value])" #suffix><CountBadge :c="countOf(SUB[t.value])" :name="SUB[t.value]" /></template>
                <template v-else-if="t.value === 'week' && navDot('Reset')" #suffix>
                  <span class="mr-2 size-2 rounded-full bg-surface-amber-7" role="img" :aria-label="navDot('Reset').label" data-reset-dot /></template>
              </SidebarItem>
            </template>
          </div>
        </template>
      </nav>
      <!-- Focus on an area: the pinned areas as one-click lenses, then "All areas…" (the lens's picker) -->
      <div class="mt-4 flex flex-col gap-0.5" data-nav-group="focus" role="group" aria-label="Focus on an area">
        <div v-if="!nav.rail" class="px-2 py-1 text-sm text-ink-gray-6">Focus on an area</div>
        <SidebarItem v-for="a in pinnedAreas" :key="a.name" :label="a.area_name" :active="lens.area === a.name" :data-nav-pin="a.name"
          :aria-pressed="lens.area === a.name" @click="setLens({ area: lens.area === a.name ? '' : a.name })">
          <template #prefix><span class="mx-1 size-2 rounded-full" :class="dotClass(a)" aria-hidden="true" /></template>
        </SidebarItem>
        <SidebarItem v-if="!nav.rail" label="All areas…" :active="false" data-nav-all-areas @click="allAreas" />
      </div>
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
import { PLACES, PLAN_TABS, SETTINGS, planPath } from '@/lib/nav'
import { activePlace, activePlanTab, nav, setPlanOpen, setRail } from '@/lib/sidebar'
import { dotClass, lens, lensAreaName, pinnedAreas, setLens } from '@/lib/lens'
import { lensMenu } from './lens/lensMenu'
import { canWrite, store } from '@/lib/store'
import { newMenuItems, navCount, navDot } from '@/lib/newMenu'

const emit = defineEmits(['logout', 'shortcuts'])
const router = useRouter()
const newMenu = computed(() => newMenuItems())
// the counts the sidebar shows, by the item they sit on: Inbox; Tasks and Someday under Plan
const SUB = { tasks: 'Tasks', someday: 'Someday' }
const countOf = (label) => (label ? navCount(label) : null)
// Plan opens to its tabs while one of them is open, or when the person opened it
const planShown = computed(() => nav.planOpen || activePlace.value === '/plan')
const firstName = computed(() => (store.fullName || store.user || '').split(' ')[0])
// a count is a door: it opens the list with exactly that many rows
const CountBadge = (p) => h(RouterLink, { class: 'relative mr-1.5 rounded-full focus-visible:focus-ring', to: p.c.to, 'aria-label': p.c.label, 'data-door': p.c.door,
  'data-nav-count': p.name, 'data-count-door': '', 'data-count-n': p.c.n, 'data-count-label': p.c.count.label, 'data-count-key': 'nav:' + p.name,
  onClick: (e) => e.stopPropagation() }, () => h(Badge, { label: p.c.n }))
CountBadge.props = ['c', 'name']
// the rail is a desktop choice: the library collapses the sidebar by itself on a narrow window, which is not remembered
const onCollapse = (v) => { if (window.innerWidth >= 768) setRail(!!v) }
// "All areas…" opens the lens's picker, which lists every area
function allAreas() {
  document.querySelector('[data-slot="sidebar-header"] button')?.click()
}
const userMenu = computed(() => [
  { label: 'Profile and appearance', icon: 'lucide-user', onClick: () => router.push({ path: '/settings', query: { tab: 'profile' } }) },
  { label: 'Keyboard shortcuts', icon: 'lucide-keyboard', onClick: () => emit('shortcuts') },
  { label: 'Log out', icon: 'lucide-log-out', onClick: () => emit('logout') },
])
</script>
