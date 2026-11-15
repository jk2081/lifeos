<template>
  <div class="sp-back" @click.self="$emit('close')">
    <div class="spal" role="dialog" aria-label="Search">
      <input ref="input" v-model="text" class="inp" style="width: 100%; height: 40px" placeholder="Search notes, tasks, inbox items, chats and the vault"
        aria-label="Search" @keydown.down.prevent="move(1)" @keydown.up.prevent="move(-1)" @keydown.enter="go(results[active])" @keydown.esc="$emit('close')" />
      <div class="res">
        <a v-for="(r, i) in results" :key="r.ref_name + r.kind" href="#" class="hit" :class="{ on: i === active }" @mouseenter="active = i" @click.prevent="go(r)">
          <div style="display: flex; gap: 8px; align-items: baseline">
            <b style="font-weight: 500; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{{ r.title || 'Untitled' }}</b>
            <span class="pl n">{{ KIND[r.kind] || r.kind }}</span>
          </div>
          <div class="mt">{{ [multi && r.space, r.area_name, short(r.record_date, true), r.is_archived ? 'archived' : ''].filter(Boolean).join(' · ') }}</div>
          <div v-if="r.snippet" class="mt snip">{{ r.snippet }}</div>
        </a>
        <div v-if="searched && !results.length" class="empty"><b>Nothing found for “{{ searched }}”.</b>Try fewer words{{ archived ? '' : ', or include archived records' }}.</div>
        <div v-else-if="!text.trim()" class="empty"><b>Search everything you can see.</b>Type a word from a title, a note or a transcript. Use ↑ ↓ and Enter.</div>
      </div>
      <label class="mt" style="display: flex; gap: 6px; align-items: center; margin-top: 8px"><input v-model="archived" type="checkbox" class="ck" style="margin: 0" /> Include archived</label>
    </div>
  </div>
</template>
<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { openRef, refOf } from '@/lib/pane'

const emit = defineEmits(['close'])
const KIND = { Inbox: 'Inbox item', 'Journal Page': 'Journal page', 'Month Plan': 'Month plan' }
const router = useRouter()
const input = ref(null)
const text = ref('')
const results = ref([])
const active = ref(0)
const searched = ref('')
const archived = ref(false)
const multi = computed(() => store.spaces.length > 1)
let timer = null
let seq = 0

async function run() {
  const q = text.value.trim()
  if (!q) {
    results.value = []
    searched.value = ''
    return
  }
  const mine = ++seq
  try {
    const res = await api('search.query', { text: q, limit: 20, include_archived: archived.value ? 1 : 0 })
    if (mine !== seq) return
    results.value = res.results
    active.value = 0
    searched.value = q
  } catch (e) {
    results.value = []
  }
}
watch([text, archived], () => {
  clearTimeout(timer)
  timer = setTimeout(run, 180)
})
function move(n) {
  if (results.value.length) active.value = (active.value + n + results.value.length) % results.value.length
}
function go(r) {
  if (!r) return
  if (r.space && r.space !== store.space) store.space = r.space
  // the result opens in the pane over the screen you are on
  const ref = refOf(r.ref_doctype, r.ref_name)
  ref ? openRef(ref) : router.push(r.route)
  emit('close')
}
onMounted(() => input.value?.focus())
</script>
<style scoped>
.sp-back { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.25); z-index: 60; display: flex; justify-content: center; align-items: flex-start; padding: 10vh 16px 0; }
.spal { width: min(640px, 100%); background: var(--bg); border: 1px solid var(--line); border-radius: 12px; padding: 14px; box-shadow: var(--shadow); }
.res { max-height: 56vh; overflow-y: auto; margin-top: 8px; }
.hit { display: block; padding: 8px 10px; border-radius: 8px; color: var(--ink); }
.hit.on { background: var(--fill); }
.snip { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
