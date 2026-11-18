<template>
  <div v-if="screenError" class="page-body" role="alert" data-screen-error>
    <Card class="flex max-w-xl flex-col items-start gap-3">
      <h1 class="text-lg-semibold text-ink-gray-9">{{ chunk ? 'A newer version of Life OS is available.' : 'This screen could not be shown.' }}</h1>
      <p class="text-base text-ink-gray-7">{{ chunk ? 'Reload to get it. Nothing you saved is lost.' : 'The rest of Life OS still works: pick another place, or reload this screen.' }}</p>
      <Button variant="solid" label="Reload" data-screen-error-reload @click="reload" />
      <p class="text-sm text-ink-gray-6">Error reference <span class="font-mono" data-screen-error-ref>{{ screenError.reference }}</span></p>
    </Card>
  </div>
</template>
<script setup>
// The message of a screen that failed (bug fix 1), drawn by ScreenBoundary beside the page. It is its own component so
// that showing it re-renders only this, never the failed page's tree.
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import Card from './ui/Card.vue'
import { screenError } from '@/lib/screenError'

const chunk = computed(() => screenError.value?.kind === 'chunk')

function reload() {
  const href = screenError.value?.href
  if (href) window.location.assign(href)
  else window.location.reload()
}
</script>
