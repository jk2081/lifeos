<template>
  <a :href="href" @click.prevent="openRef(to)"><slot /></a>
</template>
<script setup>
// A link to a record that opens it in the Drawer over the screen (`to` is a layer reference such as `goal:<id>`). The href is the screen's own address
// with `?open=`, so a middle click or a copied link opens the same layer.
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { openRef } from '@/lib/pane'
const props = defineProps({ to: { type: String, required: true } })
const route = useRoute()
const router = useRouter()
const href = computed(() => router.resolve({ path: route.path, query: { ...route.query, open: props.to, under: undefined } }).href)
</script>
