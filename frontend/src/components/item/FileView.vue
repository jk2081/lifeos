<template>
  <div data-file-view>
    <div v-if="kind === 'image'" class="max-h-[520px] overflow-auto rounded-5 border border-outline-gray-1 bg-surface-gray-1" :class="zoom ? 'cursor-zoom-out' : 'cursor-zoom-in'" @click="zoom = !zoom">
      <img class="block h-auto" :class="zoom ? 'w-[220%] max-w-none' : 'w-full'" :src="preview || file.file_url" :alt="file.file_name" />
    </div>
    <audio v-else-if="kind === 'audio'" :src="file.file_url" controls class="w-full"></audio>
    <object v-else-if="kind === 'pdf'" :data="file.file_url" type="application/pdf" class="block h-[520px] w-full rounded-5 border border-outline-gray-1">
      <a class="text-ink-blue-8 hover:underline" :href="file.file_url" target="_blank" rel="noopener">Open {{ file.file_name }}</a>
    </object>
    <div class="mt-1.5 break-words text-sm text-ink-gray-6">
      <a class="text-ink-blue-8 hover:underline" :href="file.file_url" target="_blank" rel="noopener">{{ file.file_name }}</a> · {{ fileSize(file.file_size) }}
      <span v-if="kind === 'image'"> · click the image to zoom</span>
    </div>
    <FileVersions :file="file" />
  </div>
</template>
<script setup>
// One file of an inbox item as it arrived: an image (click to zoom), audio, a PDF, or a link, with its earlier versions
// (issue 7). Shared by the Review screen and the item page (issue 10). `preview` is the item's smaller image, if it has one.
import { computed, ref } from 'vue'
import FileVersions from '../FileVersions.vue'
import { fileKind, fileSize } from '@/lib/upload'

const props = defineProps({ file: Object, preview: String })
const zoom = ref(false)
const kind = computed(() => fileKind(props.file.file_name))
</script>
