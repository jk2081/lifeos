<template>
  <PageHead title="How Life OS works" sub="Plug in where information comes from. The Brain sorts it onto your goals. You only see what to do, and what it could not place.">
    <Button v-if="!store.isAgent && ladder.dismissed && !ladder.complete" label="Show setup card" data-setup-undo @click="dismissLadder(true)" />
  </PageHead>
  <div class="flex flex-col gap-8 px-4 pb-8 pt-4 md:px-7" data-how>
    <div class="grid gap-3 md:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] md:items-center" data-how-flow>
      <template v-for="(s, i) in FLOW" :key="s.title">
        <span v-if="i" class="lucide-arrow-right hidden size-5 text-ink-gray-5 md:block" aria-hidden="true" />
        <div class="h-full rounded-5 border p-4" :class="s.brain ? 'border-outline-violet-1 bg-surface-violet-1' : s.see ? 'border-outline-gray-9' : 'border-outline-gray-2'" :data-how-step="s.title">
          <div class="text-sm text-ink-gray-6">{{ s.kicker }}</div>
          <div class="mt-1 text-base-medium text-ink-gray-9">{{ s.title }}</div>
          <p class="mt-2 text-sm text-ink-gray-7">{{ s.text }}</p>
        </div>
      </template>
    </div>
    <section aria-labelledby="ladder-h">
      <SectionHead id="ladder-h">The ladder</SectionHead>
      <p class="mt-1 text-sm text-ink-gray-6">Each level opens when the one before it is in use. It teaches working with agents one step at a time.</p>
      <ol class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6" data-ladder>
        <li v-for="l in levels" :key="l.level" class="rounded-5 border p-3" :class="[l.mark === 'next' ? 'border-outline-gray-9' : 'border-outline-gray-2', l.mark === 'later' && 'opacity-60']"
          :data-ladder-level="l.level" :data-ladder-mark="l.mark">
          <div class="text-sm text-ink-gray-6">Level {{ l.level }}<template v-if="l.mark === 'next'"> · next</template><template v-else-if="l.mark === 'now'"> · you are here</template><template v-else-if="l.mark === 'done'"> · done</template></div>
          <div class="mt-1 text-base-medium text-ink-gray-9">{{ l.title }}</div>
          <div class="mt-1 text-sm text-ink-gray-7">{{ l.hint }}</div>
          <div class="mt-2 text-sm text-ink-gray-7">→ {{ l.gain }}</div>
          <RouterLink v-if="l.mark === 'next'" class="mt-2 inline-block text-sm text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="l.to" data-ladder-go>Go</RouterLink>
        </li>
      </ol>
    </section>
  </div>
</template>
<script setup>
import SectionHead from '@/components/ui/SectionHead.vue'
// How it works (issue 26): Sources → Brain → Plan → what you see, and the ladder with the current level marked "next".
import { computed, onMounted } from 'vue'
import { Button } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import { store } from '@/lib/store'
import { ladder, loadLadder, dismissLadder } from '@/lib/ladder'

const FLOW = [
  { kicker: '1 · Sources (in Brain)', title: 'Where information comes from', text: 'Email · Calendar · Your assistant · Claude · Photos, files and voice you capture' },
  { kicker: '2 · Brain', title: 'Reads and sorts', brain: true, text: 'Pulls out people, dates and promises · picks area and goal · proposes tasks and notes · links related things · says how sure it is' },
  { kicker: '3 · Plan', title: 'Your areas and goals', text: 'The shelves everything is filed on. Clearer goals, better sorting.' },
  { kicker: 'What you see', title: 'Today, Brain, Goals, Library', see: true, text: 'Today: what to do. Brain: what came in and what needs you. Goals: where life is going. Library: what you know.' },
]
// the level you are on is done once the next one opens; the step you are working towards is "next"
const levels = computed(() => (ladder.levels || []).map((l) => {
  const done = ladder.done?.find((d) => d.level === l.level)?.done
  const mark = ladder.complete || done ? 'done' : ladder.next?.level === l.level ? 'next' : l.level === ladder.level ? 'now' : 'later'
  return { ...l, mark }
}))
onMounted(loadLadder)
</script>
