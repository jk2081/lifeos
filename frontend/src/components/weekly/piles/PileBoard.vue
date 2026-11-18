<template>
  <div class="flex flex-col gap-4" data-pile-board :data-pile-key="pkey">
    <NeedsYou v-if="s && !hideCards" :rows="s.needs" @settle="settle" @undo="undo" />
    <section v-if="s && !hideCards" class="flex flex-col gap-2">
      <h2 class="text-base-medium text-ink-gray-9">{{ heading }} · {{ total }}</h2>
      <div class="grid gap-3 md:grid-cols-3">
        <PileCard v-for="p in PILES" :key="p" :pile="p" :pkey="pkey" :p="s.piles[p]" :show="s.needs_left > 2 ? 2 : 3" @open="open(p)" @undo="undoPile(p)" />
      </div>
    </section>
    <PileDrawer :pile="drawerPile" :pkey="pkey" :data="drawer" :switchable="switchable" @close="drawerPile = null" @switch="open"
      @settle="settle" @undo="undo" @accept="accept" />
  </div>
</template>
<script setup>
// Needs you and the three piles (set 8), one component for Library (Inbox items) and Tasks (stuck and waiting). The drawer
// opens a pile; accepting it closes the drawer and the card shows its done state. Everything goes through the review's
// `act`, which saves at once.
import { computed, ref, watch } from 'vue'
import NeedsYou from './NeedsYou.vue'
import PileCard from './PileCard.vue'
import PileDrawer from './PileDrawer.vue'
import { useReview } from '@/lib/review'

const PILES = ['keep', 'park', 'letgo']
const props = defineProps({ pkey: String, heading: String, hideCards: Boolean, switchable: Boolean })
const emit = defineEmits(['summary'])
const r = useReview()
const s = ref(null)
const drawerPile = ref(null)
const drawer = ref(null)
const total = computed(() => (s.value ? PILES.reduce((n, p) => n + s.value.piles[p].count, 0) : 0))

async function load() {
  s.value = await r.read('pile_summary', { key: props.pkey })
  emit('summary', s.value)
  if (drawerPile.value) drawer.value = await r.read('pile_drawer', { key: props.pkey, pile: drawerPile.value })
}
async function open(p) {
  drawerPile.value = p
  drawer.value = null
  drawer.value = await r.read('pile_drawer', { key: props.pkey, pile: p })
}
async function settle(row, decision, chase) {
  const out = await r.act('pile_settle', { key: props.pkey, ref: row.ref, decision, chase: chase ?? undefined })
  s.value = out.summary
  emit('summary', s.value)
  if (drawerPile.value) drawer.value = await r.read('pile_drawer', { key: props.pkey, pile: drawerPile.value })
}
async function undo(row) {
  const out = await r.act('pile_undo', { key: props.pkey, ref: row.ref })
  s.value = out.summary
  emit('summary', s.value)
  if (drawerPile.value) drawer.value = await r.read('pile_drawer', { key: props.pkey, pile: drawerPile.value })
}
async function accept(p) {
  const out = await r.act('pile_accept', { key: props.pkey, pile: p })
  s.value = out.summary
  emit('summary', s.value)
  drawerPile.value = null // accepting closes the drawer and returns to the tab, where the card shows its done state
}
async function undoPile(p) {
  const out = await r.act('pile_undo', { key: props.pkey, pile: p }, 'Undone.')
  s.value = out.summary
  emit('summary', s.value)
}
watch(() => r.head?.name, load, { immediate: true })
defineExpose({ open, load })
</script>
