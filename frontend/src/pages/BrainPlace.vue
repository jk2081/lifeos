<template>
  <NeedsYou v-if="current === 'needs-you'" />
  <Inbox v-else-if="current === 'queue'" />
  <Sources v-else-if="current === 'activity'" place="captures" screen="brain-activity" />
  <template v-else-if="current === 'sources'">
    <PageHead title="Sources" sub="Where information comes from. The Brain reads only what you switch on." />
    <div class="page-body max-w-4xl" data-brain-sources><ConnectionsSection :space="store.space" :writable="canWrite() && !store.isAgent" /></div>
  </template>
  <Outbox v-else-if="current === 'outbox'" />
  <PlaceLinks :links="LINKS" label="More in the Brain" />
</template>
<script setup>
// The Brain, one of the four places (issue 14): Needs you (issue 17: what the Brain asks you to decide), Activity (everything that came in
// and what was made from it) and Sources (the connections). The tabs are paths (/brain, /brain/activity); every screen
// open here shows them under its header. The Outbox and the Queue (the old Inbox list: captures waiting for the agent or failed) are pages of the Brain, linked under every tab. Until each tab's own
// issue lands, it shows the nearest screen.
import { computed, provide } from 'vue'
import { useRouter } from 'vue-router'
import Inbox from '@/pages/Inbox.vue'
import NeedsYou from '@/components/brain/NeedsYou.vue'
import Sources from '@/pages/Sources.vue'
import Outbox from '@/pages/Outbox.vue'
import PageHead from '@/components/PageHead.vue'
import PlaceLinks from '@/components/PlaceLinks.vue'
import ConnectionsSection from '@/components/settings/ConnectionsSection.vue'
import { BRAIN_TABS, brainPath, withPage } from '@/lib/nav'
import { navCount } from '@/lib/newMenu'
import { canWrite, store } from '@/lib/store'

const props = defineProps({ tab: String })
const router = useRouter()
const current = computed(() => props.tab || 'needs-you')
const LINKS = [{ key: 'queue', label: 'Queue: every capture and where it is', icon: 'lucide-list', to: '/brain/queue' },
  { key: 'outbox', label: 'Outbox: what went out', icon: 'lucide-send', to: '/brain/outbox' }]
// Needs you carries the same count as the sidebar's Brain
const tabs = computed(() => BRAIN_TABS.map((t) => (t.value === 'needs-you' ? { ...t, count: navCount('Brain')?.n ?? 0, noun: 'to review' } : t)))
const PAGES = { outbox: 'Outbox', queue: 'Queue' }
provide('placeTabs', computed(() => ({ tabs: withPage(tabs.value, current.value, PAGES), current: current.value, label: 'Brain',
  set: (v) => router.push(brainPath(v)) })))
</script>
