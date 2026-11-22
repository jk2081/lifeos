<template>
  <PageHead title="Save to Life OS" sub="Something shared from another app" :crumb="{ to: '/brain', label: 'Brain', here: 'Share' }" />
  <div class="page-body" data-share>
    <div class="mx-auto flex w-full max-w-[640px] flex-col gap-4">
      <Skeleton v-if="share === undefined" class="h-24 w-full rounded-4" />
      <Card v-else-if="!share" data-share-empty><Empty title="Nothing was shared.">
        In another app, choose Share, then Life OS, and it opens here. Or capture something now.<br />
        <Button class="mt-2" variant="solid" icon-left="lucide-plus" label="Capture" @click="store.captureOpen = true" /></Empty></Card>
      <template v-else>
        <Card class="flex flex-col gap-2" data-share-what>
          <div v-if="share.title" class="text-base-medium text-ink-gray-9" data-share-title>{{ share.title }}</div>
          <p v-if="share.text" class="whitespace-pre-wrap break-words text-base text-ink-gray-8" data-share-text>{{ share.text }}</p>
          <a v-if="safeUrl" class="break-all text-base text-ink-blue-8 hover:underline" :href="safeUrl" target="_blank" rel="noopener noreferrer" data-share-url>{{ share.url }}</a>
          <div v-for="(f, i) in share.files" :key="i" class="flex items-center gap-3" data-share-file>
            <img v-if="previews[i]" :src="previews[i]" :alt="f.name" class="size-16 rounded-3 object-cover" />
            <span v-else class="lucide-file size-6 text-ink-gray-6" aria-hidden="true" />
            <span class="min-w-0 break-all text-base text-ink-gray-8">{{ f.name }} <span class="text-ink-gray-6">{{ fileSize(f.blob.size) }}</span></span>
          </div>
        </Card>
        <FormControl v-model="instruction" type="text" label="Instruction (optional)" placeholder="What should the Brain do with it? For example: summarise and pull out to-dos"
          data-share-instruction />
        <p v-if="!canWrite()" class="text-sm text-ink-gray-7">You can read {{ store.space }} but not add to it.</p>
        <div class="flex flex-wrap gap-2">
          <Button variant="solid" label="Save" :loading="busy" :disabled="busy || !canWrite()" data-share-save @click="save" />
          <Button label="Discard" :disabled="busy" data-share-discard @click="discard" />
        </div>
      </template>
    </div>
  </div>
</template>
<script setup>
// The share target's screen (issue 50). The service worker kept what another app shared in IndexedDB on this phone; nothing has
// been sent. Save makes a capture (source Phone) the same way + Capture does: sent now, or kept and sent when online.
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, FormControl, Skeleton, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import { errorText } from '@/lib/api'
import { dropShare, getShare, latestShare, submitCapture } from '@/lib/offline'
import { fileSize } from '@/lib/upload'
import { canWrite, store } from '@/lib/store'

const route = useRoute()
const router = useRouter()
const share = ref(undefined)
const previews = ref([])
const instruction = ref('')
const busy = ref(false)
const safeUrl = computed(() => (/^https?:\/\//i.test(share.value?.url || '') ? share.value.url : ''))

onMounted(async () => {
  let s = null
  try {
    s = (route.query.id && (await getShare(String(route.query.id)))) || (await latestShare()) || null
  } catch { /* no database: nothing shared */ }
  // a text or link shared without the service worker arrives as address parameters
  if (!s && (route.query.text || route.query.url || route.query.title)) {
    s = { id: '', title: String(route.query.title || ''), text: String(route.query.text || ''), url: String(route.query.url || ''), files: [] }
  }
  share.value = s
  previews.value = (s?.files || []).map((f) => (f.type?.startsWith('image/') ? URL.createObjectURL(f.blob) : ''))
})
onUnmounted(() => previews.value.forEach((u) => u && URL.revokeObjectURL(u)))

async function save() {
  const s = share.value
  busy.value = true
  try {
    const text = [s.text, s.url && !s.text.includes(s.url) ? s.url : ''].filter(Boolean).join('\n').trim()
    const first = s.files[0]?.name
    const title = (s.title || (first ? (s.files.length > 1 ? `${first} and ${s.files.length - 1} more` : first) : text.split('\n')[0]) || 'Shared').slice(0, 80)
    const how = await submitCapture({ title, source_type: 'Phone', space: store.space, instruction: instruction.value, raw_text: text, source_url: safeUrl.value || undefined,
      intent: 'Process', files: s.files.map((f) => new File([f.blob], f.name, { type: f.type })) })
    if (s.id) await dropShare(s.id)
    toast.success(how === 'sent' ? 'Sent to the Brain. It files it and asks you only if it needs to.' : 'Kept on this phone. It is sent when you are back online.')
    router.replace('/brain')
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.value = false
  }
}
async function discard() {
  if (share.value?.id) await dropShare(share.value.id)
  router.replace('/today')
}
</script>
