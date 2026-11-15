<template>
  <template v-if="d">
    <PageHead :title="d.page_number ? `Journal page ${d.page_number}` : 'Journal page'" :crumb="{ to: '/journal/pages', label: 'Pages', here: long(d.page_date, true) }" :sub="long(d.page_date, true)">
      <button v-if="d.inbox_item" class="bt s" type="button" @click="openRef('inbox:' + d.inbox_item)">Open the inbox item</button>
    </PageHead>
    <div class="bd"><div class="cols">
      <div class="half"><section><h2 class="sh">Page</h2>
        <div v-if="d.image" class="imgwrap" :class="{ zoom }" @click="zoom = !zoom"><img :src="d.image" alt="Photographed journal page" /></div>
        <div v-else class="cd"><Empty title="No image." hint="This page has a transcript but no photograph." /></div></section></div>
      <div class="half">
        <section><h2 class="sh">Transcript <a v-if="writable && !editing" href="#" class="more" @click.prevent="start">Edit</a></h2>
          <div class="cd">
            <template v-if="editing"><textarea v-model="draft" class="inp" rows="16" style="width: 100%"></textarea>
              <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px"><button class="bt s" type="button" @click="editing = false">Cancel</button>
                <button class="bt p" type="button" @click="save">Save transcript</button></div></template>
            <Md v-else-if="d.transcript_md" :text="d.transcript_md" read />
            <Empty v-else title="No transcript." hint="Use Edit to type what the page says." />
          </div></section>
        <section><h2 class="sh">Created from this page</h2>
          <div class="cd list"><div v-for="c in d.created" :key="c.route" class="rw rowlink" @click="openRoute(c.route)"><div class="grow"><div class="ttl">{{ c.title }}</div><div class="mt">{{ c.kind }}</div></div></div>
            <Empty v-if="!d.created.length" title="Nothing else was created from this page." hint="Tasks, ticks and check-ins accepted from the same photo are listed here." /></div></section>
      </div>
    </div></div>
  </template>
  <div v-else-if="missing" class="bd"><div class="cd"><Empty title="This page was not found." hint="It may belong to another space." /></div></div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import PageHead from '@/components/PageHead.vue'
import Md from '@/components/Md.vue'
import Empty from '@/components/Empty.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { long } from '@/lib/dates'
import { openRef, openRoute } from '@/lib/pane'

const props = defineProps({ id: String })
const d = ref(null)
const missing = ref(false)
const zoom = ref(false)
const editing = ref(false)
const draft = ref('')
const writable = computed(() => store.spaces.find((s) => s.name === d.value?.space)?.access === 'Write')
function start() {
  draft.value = d.value.transcript_md
  editing.value = true
}
async function save() {
  if (await tryCall(() => api('journal.save_page_transcript', { page: d.value.name, transcript_md: draft.value }), 'Transcript saved.')) {
    d.value.transcript_md = draft.value
    editing.value = false
  }
}
onMounted(async () => {
  try {
    d.value = await api('journal.page_detail', { page: props.id })
  } catch (e) {
    missing.value = true
  }
})
</script>
<style scoped>
.imgwrap { border: 1px solid var(--outline-gray-1); border-radius: 10px; background: var(--surface-gray-1); overflow: auto; max-height: 80vh; cursor: zoom-in; }
.imgwrap img { display: block; width: 100%; height: auto; }
.imgwrap.zoom { cursor: zoom-out; }
.imgwrap.zoom img { width: 220%; max-width: none; }
</style>
