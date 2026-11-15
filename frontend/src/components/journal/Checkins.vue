<template>
  <div v-if="d" class="page-body">
    <div class="cols">
      <div class="half">
        <section v-if="canWrite()">
          <SectionHead>{{ editingName ? 'Edit check-in' : 'New check-in' }}</SectionHead>
          <Card>
            <DatePicker v-model="form.date" class="mb-3 max-w-[200px]" label="Date" />
            <div class="scores">
              <div></div><div class="text-sm text-ink-gray-6">Habits</div><div class="text-sm text-ink-gray-6">Situation</div><div class="note-head text-sm text-ink-gray-6">Note</div>
              <template v-for="s in form.scores" :key="s.dimension">
                <label class="font-medium text-ink-gray-8" :for="'h-' + s.dimension">{{ s.dimension_name }}</label>
                <TextInput :id="'h-' + s.dimension" v-model="s.habits" inputmode="decimal" placeholder="0-10" :aria-label="`${s.dimension_name}, habits`" />
                <TextInput v-model="s.situation" inputmode="decimal" placeholder="0-10" :aria-label="`${s.dimension_name}, situation`" />
                <div class="note"><TextInput v-model="s.note" :aria-label="`${s.dimension_name}, note`" /></div>
              </template>
            </div>
            <p class="mb-3 mt-2 text-sm text-ink-gray-6">A score is 0 to 10. Type one number, or a range such as 2-3.</p>
            <FormControl v-model="form.reflection_md" type="textarea" label="Reflection" :rows="4" />
            <div class="mt-3 flex justify-end gap-2">
              <Button v-if="editingName" label="Cancel" @click="reset" />
              <Button variant="solid" label="Save check-in" @click="save" />
            </div>
          </Card>
        </section>
        <section>
          <SectionHead>Past check-ins</SectionHead>
          <Card flush>
            <Row v-for="c in d.checkins" :key="c.name">
              <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ long(c.date, true) }}</div>
                <div class="text-sm text-ink-gray-6">{{ c.scores.map((s) => `${s.dimension_name} ${range(s.habits_low, s.habits_high)}/${range(s.situation_low, s.situation_high)}`).join(' · ') }}</div>
                <Md v-if="c.reflection_md" class="mt-1.5" :text="c.reflection_md" /></div>
              <Button v-if="canWrite()" variant="ghost" label="Edit" @click="edit(c)" />
            </Row>
            <Empty v-if="!d.checkins.length" title="No check-ins yet." hint="Score each dimension above, or upload the journal page and let the agent propose the check-in." />
          </Card>
        </section>
      </div>
      <div class="half">
        <section>
          <SectionHead>Over time
            <template #action><span class="inline-flex items-center gap-1.5 font-normal text-ink-gray-7">
              <svg class="size-2.5" viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="5" r="5" fill="var(--ink-blue-7)" /></svg>Habits
              <svg class="ml-2 size-2.5" viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="5" r="5" fill="var(--ink-amber-7)" /></svg>Situation</span></template></SectionHead>
          <div v-if="charts.length" class="charts">
            <Card v-for="s in charts" :key="s.dimension"><div class="mb-1 font-medium text-ink-gray-9">{{ s.dimension_name }}</div>
              <LineChart :points="s.points" :label="`${s.dimension_name}: habits and situation scores over time`" /></Card>
          </div>
          <Card v-else><Empty title="Nothing to chart yet." hint="Each dimension gets a line chart of the midpoint of its scores once there is a check-in." /></Card>
          <p v-if="charts.length" class="mt-2 text-sm text-ink-gray-6">Each point is the midpoint of the range you wrote. The same numbers are listed under Past check-ins.</p>
        </section>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Button, DatePicker, FormControl, TextInput } from 'frappe-ui'
import Md from '@/components/Md.vue'
import Empty from '@/components/Empty.vue'
import LineChart from '@/components/LineChart.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { long } from '@/lib/dates'

const emit = defineEmits(['sub'])
const d = ref(null)
const editingName = ref('')
const form = reactive({ date: store.today, scores: [], reflection_md: '' })
const range = (lo, hi) => (lo == null ? '—' : lo === hi ? String(lo) : `${lo}-${hi}`)
const charts = computed(() => d.value.series.filter((s) => s.points.length))

function reset() {
  editingName.value = ''
  Object.assign(form, { date: store.today, reflection_md: '', scores: d.value.dimensions.map((x) => ({ dimension: x.name, dimension_name: x.dimension_name, habits: '', situation: '', note: '' })) })
}
function edit(c) {
  editingName.value = c.name
  const val = (lo, hi) => (lo == null ? '' : range(lo, hi))
  Object.assign(form, { date: c.date, reflection_md: c.reflection_md, scores: d.value.dimensions.map((x) => {
    const s = c.scores.find((y) => y.dimension === x.name)
    return { dimension: x.name, dimension_name: x.dimension_name, habits: s ? val(s.habits_low, s.habits_high) : '', situation: s ? val(s.situation_low, s.situation_high) : '', note: s?.note || '' }
  }) })
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
async function save() {
  const res = await tryCall(() => api('journal.save_checkin', { space: store.space, name: editingName.value || undefined, date: form.date, scores: form.scores, reflection_md: form.reflection_md }), 'Check-in saved.')
  if (res) load()
}
async function load() {
  const res = await tryCall(() => api('journal.checkins', { space: store.space }))
  if (res) {
    d.value = res
    reset()
  }
}
onMounted(() => {
  emit('sub', 'Two scores for each life dimension: your habits and your situation')
  load()
})
</script>
<style scoped>
/* geometry only: the score form's columns (name, habits, situation, note; the note drops to its own line on a phone) and the chart tiles */
.scores { display: grid; grid-template-columns: minmax(110px, 1.4fr) 72px 72px minmax(0, 2fr); gap: 6px 8px; align-items: center; }
.charts { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
@media (max-width: 767px) { .scores { grid-template-columns: minmax(0, 1fr) 64px 64px; } .scores > .note { grid-column: 1 / -1; } .scores > .note-head { display: none; } }
</style>
