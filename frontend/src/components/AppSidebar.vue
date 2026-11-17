<template>
  <!-- The sidebar in groups: space switcher, Search and New, the daily places, Plan, the space's Areas, Records, and
       Archive and Settings pinned at the bottom. Plan, Areas and Records collapse from their heading; the whole bar
       collapses to an icon rail. Which groups and parent areas are open, and the rail, are remembered per user. -->
  <Sidebar :collapsible="true" :collapsed="nav.rail" width="232px" aria-label="Sections" data-sidebar @update:collapsed="onCollapse">
    <!-- the lens: the space and area every place narrows to (UX fixes, set 6) -->
    <SidebarHeader :title="store.space || 'No space'" :subtitle="lensAreaName" :menu-items="lensMenu" data-lens-picker />
    <!-- + New; Search moved to the Search or ask box in every screen's header (UX fixes, set 5) -->
    <div class="px-2 pb-1 pt-1" :class="nav.rail && 'flex flex-col items-center'">
      <Dropdown v-if="canWrite()" :options="newMenu">
        <Button v-if="nav.rail" icon="lucide-plus" label="New" variant="solid" tooltip="New" data-nav-new />
        <Button v-else class="w-full" icon-left="lucide-plus" label="New" variant="solid" data-nav-new />
      </Dropdown>
    </div>
    <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 pb-2" data-nav-groups>
      <template v-for="g in GROUPS" :key="g.key">
        <!-- Focus on an area: the pinned areas as one-click lens shortcuts (UX fixes, set 6), then "All areas…" -->
        <div v-if="g.key === 'areas'" class="mt-2 flex flex-col gap-0.5" data-nav-group="focus" role="group" aria-label="Focus on an area">
          <div v-if="!nav.rail" class="px-2 py-1 text-sm text-ink-gray-6">Focus on an area</div>
          <SidebarItem v-for="a in pinnedAreas" :key="a.name" :label="a.area_name" :active="lens.area === a.name" :data-nav-pin="a.name"
            :aria-pressed="lens.area === a.name" @click="setLens({ area: lens.area === a.name ? '' : a.name })">
            <template #prefix><span class="mx-1 size-2 rounded-full" :class="dotClass(a)" aria-hidden="true" /></template>
          </SidebarItem>
          <SidebarItem v-if="!nav.rail" label="All areas…" :active="false" data-nav-all-areas @click="allAreas" />
        </div>
        <SidebarSection v-else :label="g.label || undefined" :collapsible="!!g.label" :collapsed="nav.closed.includes(g.key)" :data-nav-group="g.key"
          @update:collapsed="(v) => setGroup(g.key, v)">
          <component :is="TOOLTIPS[n.label] ? Tooltip : 'div'" v-for="n in g.items" :key="n.to" v-bind="TOOLTIPS[n.label] ? { text: TOOLTIPS[n.label], placement: 'right' } : { class: 'contents' }">
            <SidebarItem :label="n.label" :icon="n.icon" :route="n.to" :active="activeKey === n.to" :data-nav-item="n.label">
              <template v-if="countOf(n)" #suffix>
                <RouterLink class="relative mr-1.5 rounded-full focus-visible:focus-ring" :to="countOf(n).to" :aria-label="countOf(n).label" :data-door="countOf(n).door"
                  :data-nav-count="n.label" data-count-door :data-count-n="countOf(n).n" :data-count-label="countOf(n).count.label" :data-count-key="'nav:' + n.label"><Badge :label="countOf(n).n" /></RouterLink>
              </template>
            </SidebarItem>
          </component>
        </SidebarSection>
      </template>
    </div>
    <div class="flex flex-col gap-0.5 border-t border-outline-gray-1 px-2 pb-3 pt-2" data-nav-bottom>
      <SidebarItem v-for="n in BOTTOM" :key="n.to" :label="n.label" :icon="n.icon" :route="n.to" :active="activeKey === n.to" :data-nav-item="n.label">
        <template v-if="navDot(n.label)" #suffix><span class="mr-2 size-2 rounded-full bg-surface-amber-7" role="img" :aria-label="navDot(n.label).label" data-reset-dot /></template>
      </SidebarItem>
      <!-- the user, with Help (the shortcuts and where things are) and Log out -->
      <div v-if="!nav.rail" class="flex items-center gap-1" data-nav-user>
        <Dropdown class="min-w-0 flex-1" :options="userMenu">
          <Button class="w-full !justify-start" variant="ghost" :label="store.fullName || store.user" data-nav-user-menu>
            <template #prefix><Avatar size="sm" :label="store.fullName || store.user" /></template>
          </Button>
        </Dropdown>
        <Button variant="ghost" label="Help" data-nav-help @click="emit('shortcuts')" />
      </div>
      <SidebarCollapseToggle />
    </div>
  </Sidebar>
</template>
<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Avatar, Badge, Button, Dropdown, Sidebar, SidebarCollapseToggle, SidebarHeader, SidebarItem, SidebarSection, Tooltip } from 'frappe-ui'
import { BOTTOM, GROUPS, TOOLTIPS } from '@/lib/nav'
import { activeKey, nav, setGroup, setRail } from '@/lib/sidebar'
import { dotClass, lens, lensAreaName, pinnedAreas, setLens } from '@/lib/lens'
import { lensMenu } from './lens/lensMenu'
import { canWrite, store } from '@/lib/store'
import { newMenuItems, navCount, navDot } from '@/lib/newMenu'

const emit = defineEmits(['logout', 'shortcuts'])
const router = useRouter()
const newMenu = computed(() => newMenuItems())
const countOf = (n) => navCount(n.label)
// the rail is a desktop choice: the library collapses the sidebar by itself on a narrow window, which is not remembered
const onCollapse = (v) => { if (window.innerWidth >= 768) setRail(!!v) }
// "All areas…" opens the lens's picker, which lists every area
function allAreas() {
  document.querySelector('[data-lens-picker] button, [data-slot="sidebar-header"] button')?.click()
}
const userMenu = computed(() => [
  { label: 'Profile and appearance', icon: 'lucide-user', onClick: () => router.push({ path: '/settings', query: { tab: 'profile' } }) },
  { label: 'Keyboard shortcuts', icon: 'lucide-keyboard', onClick: () => emit('shortcuts') },
  { label: 'Log out', icon: 'lucide-log-out', onClick: () => emit('logout') },
])
</script>
