<template>
  <!-- a rhythm tab of Plan: a view switch between the journal's screens and the calendar, under the tab's own title -->
  <Calendar v-if="cur.cal" :key="cur.key" :view="cur.cal" :place="title" :switch-options="switchOptions" :switch-value="cur.key">
    <template #above><slot name="above" :view="cur.key" /></template>
    <template #actions><slot name="actions" /></template>
  </Calendar>
  <template v-else>
    <PageHead :title="title" :sub="sub || ' '">
      <TabButtons v-if="switchOptions.length > 1" :model-value="cur.key" :options="switchOptions" aria-label="Views" data-plan-views />
      <slot name="actions" />
      <!-- the journal's screens put their buttons here -->
      <div id="jr-actions" class="contents"></div>
    </PageHead>
    <div v-if="$slots.above" class="page-body !pb-0"><slot name="above" :view="cur.key" /></div>
    <component :is="cur.comp" :key="cur.key" @sub="(s) => (sub = s)" />
  </template>
</template>
<script setup>
// One rhythm of Plan (UX fixes, set 6): Week, Month, 12 Weeks or Year. `views` are [{ key, label, comp }] for a journal
// screen or [{ key, label, cal }] for a calendar view; the open one is `view=` in the URL, the default first unless
// `initial` says otherwise. The journal screens and the calendar are the same components as before set 6.
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { TabButtons } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Calendar from '@/components/goals/Calendar.vue'

const props = defineProps({ title: String, views: Array, initial: String })
const route = useRoute()
const sub = ref('')
const cur = computed(() => props.views.find((v) => v.key === route.query.view) || props.views.find((v) => v.key === props.initial) || props.views[0])
const switchOptions = computed(() => props.views.map((v) => ({ label: v.label, value: v.key,
  route: { path: route.path, query: { ...route.query, view: v.key, open: undefined } } })))
// The journal screens teleport their buttons into #jr-actions with `defer`: frappe-ui's PageHeader itself teleports the header
// (with `defer`) into the shell, so #jr-actions exists only after the render that mounts it (bug fix 1).
</script>
