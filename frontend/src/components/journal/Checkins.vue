<template>
  <div v-if="d" class="bd">
    <div class="cols">
      <div class="half">
        <section v-if="canWrite()">
          <h2 class="sh">{{ editingName ? 'Edit check-in' : 'New check-in' }}</h2>
          <div class="cd">
            <div class="field" style="max-width: 200px; margin-bottom: 12px"><label class="lbl" for="ci-date">Date</label><input id="ci-date" v-model="form.date" type="date" class="inp" /></div>
            <div class="scores">
              <div class="mt"></div><div class="mt">Habits</div><div class="mt">Situation</div><div class="mt">Note</div>
              <template v-for="s in form.scores" :key="s.dimension">
                <label :for="'h-' + s.dimension" style="font-weight: 500">{{ s.dimension_name }}</label>
                <input :id="'h-' + s.dimension" v-model="s.habits" class="inp" inputmode="decimal" placeholder="0-10" :aria-label="`${s.dimension_name}, habits`" />
                <input v-model="s.situation" class="inp" inputmode="decimal" placeholder="0-10" :aria-label="`${s.dimension_name}, situation`" />
                <input v-model="s.note" class="inp" :aria-label="`${s.dimension_name}, note`" />
              </template>
            </div>
            <p class="mt" style="margin: 8px 0 12px">A score is 0 to 10. Type one number, or a range such as 2-3.</p>
            <div class="field"><label class="lbl" for="ci-ref">Reflection</label><textarea id="ci-ref" v-model="form.reflection_md" class="inp" rows="4"></textarea></div>
            <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px">
              <button v-if="editingName" class="bt s" type="button" @click="reset">Cancel</button>
              <button class="bt p" type="button" @click="save">Save check-in</button>
            </div>
          </div>
        </section>
        <section>
          <h2 class="sh">Past check-ins</h2>
          <div class="cd list">
            <div v-for="c in d.checkins" :key="c.name" class="rw">
              <div class="grow"><div class="ttl">{{ long(c.date, true) }}</div>
                <div class="mt">{{ c.scores.map((s) => `${s.dimension_name} ${range(s.habits_low, s.habits_high)}/${range(s.situation_low, s.situation_high)}`).join(' · ') }}</div>
                <Md v-if="c.reflection_md" :text="c.reflection_md" style="margin-top: 6px" /></div>
              <button v-if="canWrite()" class="bt t" type="button" @click="edit(c)">Edit</button>
            </div>
            <Empty v-if="!d.checkins.length" title="No check-ins yet." hint="Score each dimension above, or upload the journal page and let the agent propose the check-in." />
          </div>
        </section>
      </div>
      <div class="half">
        <section>
          <h2 class="sh">Over time
            <span class="legend"><i style="background: var(--ink-blue-7)"></i>Habits <i style="background: var(--ink-amber-7)"></i>Situation</span></h2>
          <div v-if="charts.length" class="charts">
            <div v-for="s in charts" :key="s.dimension" class="cd"><div style="font-weight: 500; margin-bottom: 4px">{{ s.dimension_name }}</div>
              <LineChart :points="s.points" :label="`${s.dimension_name}: habits and situation scores over time`" /></div>
          </div>
          <div v-else class="cd"><Empty title="Nothing to chart yet." hint="Each dimension gets a line chart of the midpoint of its scores once there is a check-in." /></div>
          <p v-if="charts.length" class="mt" style="margin: 8px 0 0">Each point is the midpoint of the range you wrote. The same numbers are listed under Past check-ins.</p>
        </section>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import Md from '@/components/Md.vue'
import Empty from '@/components/Empty.vue'
import LineChart from '@/components/LineChart.vue'
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
.scores { display: grid; grid-template-columns: minmax(110px, 1.4fr) 72px 72px minmax(0, 2fr); gap: 6px 8px; align-items: center; }
.charts { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.legend { margin-left: auto; font-weight: 400; display: inline-flex; align-items: center; gap: 6px; color: var(--ink-gray-7); }
.legend i { width: 10px; height: 10px; border-radius: 5px; display: inline-block; margin-left: 8px; }
@media (max-width: 800px) { .scores { grid-template-columns: minmax(0, 1fr) 64px 64px; } .scores > :nth-child(4n) { grid-column: 1 / -1; } .scores > .mt:nth-child(4) { display: none; } }
</style>
