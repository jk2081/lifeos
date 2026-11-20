<template>
  <!-- Issue 7: a file filed again under the same external_id keeps its earlier versions. "3 versions, latest 19 Nov" opens the list. -->
  <div v-if="earlier.length" class="mt-1 flex flex-col items-start gap-1" data-file-versions>
    <Button variant="ghost" size="sm" icon-left="lucide-history" :label="label" :aria-expanded="open ? 'true' : 'false'" @click="open = !open" data-file-versions-toggle />
    <ul v-if="open" class="flex flex-col gap-1 pl-2 text-sm text-ink-gray-6">
      <li v-for="(v, i) in earlier" :key="v.file_url + i" class="flex flex-wrap items-center gap-x-2" data-file-version>
        <a class="text-ink-blue-8 hover:underline" :href="v.file_url" target="_blank" rel="noopener noreferrer">Version {{ earlier.length - i }}</a>
        <span>{{ dateTime(v.added) }}</span><span v-if="v.file_size">{{ fileSize(v.file_size) }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Button } from 'frappe-ui'
import { dateTime, short } from '@/lib/dates'
import { fileSize } from '@/lib/upload'

const props = defineProps({ file: { type: Object, required: true } })
const open = ref(false)
const earlier = computed(() => props.file.versions || [])
const label = computed(() => `${earlier.value.length + 1} versions, latest ${short(props.file.added)}`)
</script>
