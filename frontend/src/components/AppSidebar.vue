<template>
  <!-- The sidebar in groups: space switcher, Search and New, the daily places, Plan, the space's Areas, Records, and
       Archive and Settings pinned at the bottom. Plan, Areas and Records collapse from their heading; the whole bar
       collapses to an icon rail. Which groups and parent areas are open, and the rail, are remembered per user. -->
  <Sidebar :collapsible="true" :collapsed="nav.rail" width="232px" aria-label="Sections" data-sidebar @update:collapsed="onCollapse">
    <SidebarHeader :title="store.space || 'No space'" :subtitle="store.fullName || store.user" :menu-items="spaceMenu" />
    <!-- + New; Search moved to the Search or ask box in every screen's header (UX fixes, set 5) -->
    <div class="px-2 pb-1 pt-1" :class="nav.rail && 'flex flex-col items-center'">
      <Dropdown v-if="canWrite()" :options="newMenu">
        <Button v-if="nav.rail" icon="lucide-plus" label="New" variant="solid" tooltip="New" data-nav-new />
        <Button v-else class="w-full" icon-left="lucide-plus" label="New" variant="solid" data-nav-new />
      </Dropdown>
    </div>
    <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 pb-2" data-nav-groups>
      <template v-for="g in GROUPS" :key="g.key">
        <!-- Areas: the heading is a link to /areas with its own toggle; each area links to its page, a parent opens its sub-areas -->
        <div v-if="g.key === 'areas'" class="mt-2 flex flex-col" data-nav-group="areas" :data-state="nav.closed.includes('areas') ? 'collapsed' : 'expanded'">
          <SidebarItem v-if="nav.rail" label="Areas" icon="lucide-folder" route="/areas" :active="activeKey === 'areas' || activeKey.startsWith('area:')" data-nav-item="areas" />
          <template v-else>
            <div class="flex items-center gap-1 px-2 py-1">
              <RouterLink to="/areas" class="rounded-4 text-sm focus-visible:focus-ring" :class="activeKey === 'areas' ? 'font-medium text-ink-gray-9 underline' : 'text-ink-gray-6 hover:text-ink-gray-8'"
                :aria-current="activeKey === 'areas' ? 'page' : undefined" data-nav-heading="areas" :data-active="activeKey === 'areas' || undefined">Areas</RouterLink>
              <Button class="!size-5" variant="ghost" :icon="nav.closed.includes('areas') ? 'lucide-chevron-right' : 'lucide-chevron-down'"
                :label="nav.closed.includes('areas') ? 'Show areas' : 'Hide areas'" :aria-expanded="!nav.closed.includes('areas')" data-nav-toggle="areas"
                @click="setGroup('areas', !nav.closed.includes('areas'))" />
            </div>
            <div v-show="!nav.closed.includes('areas')" class="flex flex-col gap-0.5" role="group" aria-label="Areas">
              <template v-for="a in areaTree.slice(0, MAX_AREAS)" :key="a.name">
                <SidebarItem :label="a.area_name" :route="`/areas/${a.name}`" :active="activeKey === 'area:' + a.name" :data-nav-area="a.name">
                  <template #prefix><span class="lucide-folder size-4 text-ink-gray-6" aria-hidden="true" /></template>
                  <template v-if="a.children.length" #suffix>
                    <Button class="relative mr-0.5 !size-5" variant="ghost" :icon="nav.openAreas.includes(a.name) ? 'lucide-chevron-down' : 'lucide-chevron-right'"
                      :label="(nav.openAreas.includes(a.name) ? 'Hide' : 'Show') + ' the sub-areas of ' + a.area_name" :aria-expanded="nav.openAreas.includes(a.name)" :data-nav-expand="a.name"
                      @click.stop.prevent="setAreaOpen(a.name, !nav.openAreas.includes(a.name))" />
                  </template>
                </SidebarItem>
                <div v-if="a.children.length && nav.openAreas.includes(a.name)" class="flex flex-col gap-0.5 pl-4" role="group" :aria-label="'Sub-areas of ' + a.area_name">
                  <SidebarItem v-for="c in a.children" :key="c.name" :label="c.area_name" :route="`/areas/${c.name}`" :active="activeKey === 'area:' + c.name" :data-nav-area="c.name">
                    <template #prefix><span class="lucide-corner-down-right size-4 text-ink-gray-6" aria-hidden="true" /></template>
                  </SidebarItem>
                </div>
              </template>
              <SidebarItem v-if="areaTree.length > MAX_AREAS" label="All areas" icon="lucide-folders" route="/areas" :active="false" data-nav-all-areas />
              <div v-if="!areaTree.length" class="px-2 py-1 text-sm text-ink-gray-6">No areas in this space.</div>
            </div>
          </template>
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
      <SidebarCollapseToggle />
    </div>
  </Sidebar>
</template>
<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, Dropdown, Sidebar, SidebarCollapseToggle, SidebarHeader, SidebarItem, SidebarSection, Tooltip } from 'frappe-ui'
import { BOTTOM, GROUPS, TOOLTIPS } from '@/lib/nav'
import { MAX_AREAS, activeKey, areaTree, nav, setAreaOpen, setGroup, setRail } from '@/lib/sidebar'
import { canWrite, store } from '@/lib/store'
import { newMenuItems, navCount, navDot } from '@/lib/newMenu'

const emit = defineEmits(['logout', 'shortcuts'])
const router = useRouter()
const newMenu = computed(() => newMenuItems())
const countOf = (n) => navCount(n.label)
// the rail is a desktop choice: the library collapses the sidebar by itself on a narrow window, which is not remembered
const onCollapse = (v) => { if (window.innerWidth >= 768) setRail(!!v) }
const spaceMenu = computed(() => [
  { group: 'Spaces', options: store.spaces.map((s) => ({ label: s.name, selected: s.name === store.space, onClick: () => (store.space = s.name) })) },
  { group: store.fullName || store.user, options: [
    { label: 'Keyboard shortcuts', icon: 'lucide-keyboard', onClick: () => emit('shortcuts') },
    { label: 'Settings', icon: 'lucide-settings', onClick: () => router.push('/settings') },
    { label: 'Log out', icon: 'lucide-log-out', onClick: () => emit('logout') },
  ] },
])
</script>
