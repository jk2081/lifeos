<template>
  <NeedsYou v-if="current === 'needs-you'" />
  <Inbox v-else-if="current === 'queue'" />
  <Activity v-else-if="current === 'activity'" />
  <Sources v-else-if="current === 'captures'" place="captures" screen="brain-activity" />
  <SourcesTab v-else-if="current === 'sources'" />
  <SkillsTab v-else-if="current === 'skills'" />
  <Outbox v-else-if="current === 'outbox'" />
  <PlaceLinks :links="LINKS" label="More in the Brain" />
</template>
<script setup>
// The Brain, one of the four places (issue 14): Needs you (issue 17: what the Brain asks you to decide), Activity (everything that came in
// and what was made from it) and Sources (issue 19: what Life OS reads, switched on one by one). The tabs are paths (/brain, /brain/activity); every screen
// open here shows them under its header (Skills, issue 28, from level 5). The Outbox and the Queue (the old Inbox list: captures waiting for the agent or failed) are pages of the Brain, linked under every tab. Until each tab's own
// issue lands, it shows the nearest screen.
import { computed, provide } from 'vue'
import { useRouter } from 'vue-router'
import Inbox from '@/pages/Inbox.vue'
import NeedsYou from '@/components/brain/NeedsYou.vue'
import Sources from '@/pages/Sources.vue'
import Activity from '@/components/brain/Activity.vue'
import Outbox from '@/pages/Outbox.vue'
import PlaceLinks from '@/components/PlaceLinks.vue'
import SourcesTab from '@/components/brain/SourcesTab.vue'
import SkillsTab from '@/components/brain/SkillsTab.vue'
import { ladder, loadLadder } from '@/lib/ladder'
import { BRAIN_TABS, brainPath, withPage } from '@/lib/nav'
import { navCount } from '@/lib/newMenu'

const props = defineProps({ tab: String })
const router = useRouter()
const current = computed(() => props.tab || 'needs-you')
const LINKS = [{ key: 'queue', label: 'Queue: every capture and where it is', icon: 'lucide-list', to: '/brain/queue' },
  { key: 'captures', label: 'Captures: every source, as a list', icon: 'lucide-inbox', to: '/brain/captures' },
  { key: 'outbox', label: 'Outbox: what went out', icon: 'lucide-send', to: '/brain/outbox' }]
// Needs you carries the same count as the sidebar's Brain
// Skills (issue 28) joins the tabs from level 5 of the ladder, "Give an agent work"; the page itself opens at any level
if (!ladder.loaded) loadLadder()
const shown = computed(() => BRAIN_TABS.filter((t) => t.value !== 'skills' || ladder.level >= 5 || props.tab === 'skills'))
const tabs = computed(() => shown.value.map((t) => (t.value === 'needs-you' ? { ...t, count: navCount('Brain')?.n ?? 0, noun: 'to review' } : t)))
const PAGES = { outbox: 'Outbox', queue: 'Queue', captures: 'Captures' }
provide('placeTabs', computed(() => ({ tabs: withPage(tabs.value, current.value, PAGES), current: current.value, label: 'Brain',
  set: (v) => router.push(brainPath(v)) })))
</script>
