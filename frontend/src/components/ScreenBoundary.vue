<template>
  <div ref="wrap" class="contents"><slot /></div>
  <ScreenErrorMessage />
</template>
<script setup>
// The error boundary around the routed page (bug fix 1). A screen that throws while it is set up or drawn shows a plain
// message with Reload and a short reference instead of a blank page, and the sidebar, the lens and navigation keep
// working. The failed page is hidden through the DOM, not re-rendered, because a failure inside Vue's own patching
// leaves its tree half built. Leaving the screen clears the message: by ordinary navigation, or, after such a failure,
// by loading the next screen afresh. Errors that do not stop the screen (event handlers, hooks) pass on unchanged.
import { onErrorCaptured, onUnmounted, useTemplateRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ScreenErrorMessage from './ScreenErrorMessage.vue'
import { clearScreenError, failScreen, isFatal, screenError } from '@/lib/screenError'

const route = useRoute()
const router = useRouter()
const wrap = useTemplateRef('wrap')

onErrorCaptured((err, instance, info) => {
  if (!isFatal(info)) return true
  failScreen(err, { info, instance })
  return false
})

watch(() => !!screenError.value, (failed) => {
  if (wrap.value) wrap.value.style.display = failed ? 'none' : ''
}, { flush: 'sync' })

// a half-built tree is not patched again (a new path, or a lens change that remounts the page): the next screen loads afresh
onUnmounted(router.beforeEach((to, from) => {
  if (!screenError.value?.hard || to.fullPath === from.fullPath) return true
  window.location.assign(router.resolve(to).href)
  return false
}))
watch(() => route.path, clearScreenError)
</script>
