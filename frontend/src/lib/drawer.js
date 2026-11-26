// The Drawer's one set of rules (issue 128): 480 px (Expand: half the window), docked beside the page from 1440 px, floating over it below that, full screen at 390 px.
import { reactive } from 'vue'
import { useMediaQuery } from '@vueuse/core'

export const drawer = reactive({ wide: false })
export const DOCK_AT = 1440
export const WIDTH = 480
export const isDocked = useMediaQuery(`(min-width: ${DOCK_AT}px)`)
export const isPhone = useMediaQuery('(max-width: 767px)')
