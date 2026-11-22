<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-page>
    <div v-if="showStrip" class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-2 md:px-7" data-review-strip>
      <span class="text-sm text-ink-gray-6">{{ due.length ? 'Due:' : 'Nothing else is due.' }}</span>
      <Button v-for="d in due" :key="d.kind" size="sm" :variant="d.kind === kind ? 'solid' : 'subtle'" :label="d.title" :title="d.text" :data-due-kind="d.kind" @click="pick(d.kind)" />
      <Button v-if="past.length" class="ml-auto" size="sm" variant="ghost" label="Past reviews" icon-left="lucide-history" data-past-open @click="pastOpen = true" />
    </div>
    <div v-if="!loaded" class="page-body"><Skeleton class="h-8 w-80" /><Skeleton class="h-64 w-full" /></div>
    <ReviewPage v-else-if="kind === 'weekly'" />
    <PeriodicReviewPage v-else :key="kind" :kind="kind" />
  </div>
  <Dialog v-model:open="pastOpen" title="Past reviews" size="lg">
    <div data-past-list>
      <div v-for="p in past" :key="p.name" class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-outline-gray-1 py-2 last:border-b-0" data-past-review :data-kind="p.kind">
        <Badge :theme="p.kind === 'Weekly' ? 'gray' : p.kind === 'Monthly' ? 'blue' : 'green'" :label="p.kind" data-past-kind />
        <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ p.title }}</span>
        <span class="text-sm tabular-nums text-ink-gray-6">{{ p.locked_on ? long(p.locked_on.slice(0, 10), true) : '' }}</span>
      </div>
      <Empty v-if="!past.length" title="No reviews yet." hint="Reviews you lock are listed here, with their kind." />
    </div>
  </Dialog>
</template>
<script setup>
// Review (issues 14 and 47): opens whichever review is due, the weekly one first and then the monthly; the 12-week review stands
// in for the weekly one in its week. A strip names what is due, and Past reviews lists every kind together with its kind.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dialog, Skeleton } from 'frappe-ui'
import Empty from '@/components/Empty.vue'
import ReviewPage from '@/components/weekly/ReviewPage.vue'
import PeriodicReviewPage from '@/components/periodic/PeriodicReviewPage.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { long } from '@/lib/dates'

const route = useRoute()
const router = useRouter()
const due = ref([])
const past = ref([])
const pastOpen = ref(false)
const loaded = ref(false)
const KINDS = ['weekly', 'monthly', '12-weeks']
// the address names a kind (?kind=monthly), or the first one due, or the weekly review
const kind = computed(() => (KINDS.includes(route.query.kind) ? route.query.kind : (loaded.value && due.value[0]?.kind) || 'weekly'))
const showStrip = computed(() => loaded.value && (due.value.length > 1 || past.value.length > 0 || kind.value !== 'weekly'))
function pick(k) { router.push({ path: '/review', query: { kind: k } }) }
async function load() {
  const res = await tryCall(() => api('periodic.due', { space: store.space }))
  if (res) { due.value = res.due; past.value = res.past }
  loaded.value = true
}
watch(() => store.space, load)
onMounted(load)
</script>
