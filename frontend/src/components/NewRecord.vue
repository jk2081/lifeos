<template>
  <Dialog v-model="open" :title="title" size="md">
    <div style="display: flex; flex-direction: column; gap: 12px">
      <div v-for="fld in fields" :key="fld.name" class="field">
        <label class="lbl" :for="'nr-' + fld.name">{{ fld.label }}</label>
        <select v-if="fld.options" :id="'nr-' + fld.name" v-model="values[fld.name]" class="inp">
          <option v-if="!fld.required" :value="undefined">—</option>
          <option v-for="o in fld.options" :key="o.value ?? o" :value="o.value ?? o">{{ o.label ?? o }}</option>
        </select>
        <textarea v-else-if="fld.type === 'textarea'" :id="'nr-' + fld.name" v-model="values[fld.name]" class="inp" rows="3"></textarea>
        <input v-else :id="'nr-' + fld.name" v-model="values[fld.name]" class="inp" :type="fld.type || 'text'" :maxlength="fld.maxlength"
          :placeholder="fld.placeholder" @keydown.enter="fld.type !== 'textarea' && submit()" />
        <div v-if="fld.help" class="mt">{{ fld.help }}</div>
      </div>
    </div>
    <template #actions>
      <div style="display: flex; gap: 8px; justify-content: flex-end">
        <button class="bt s" type="button" @click="open = false">Cancel</button>
        <button class="bt p" type="button" :disabled="busy" @click="submit">{{ action }}</button>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
// A small form dialog used for "New project", "New note", "Add event" and the like.
import { reactive, ref, watch } from 'vue'
import { Dialog, toast } from 'frappe-ui'
import { errorText } from '@/lib/api'

const props = defineProps({ modelValue: Boolean, title: String, action: { type: String, default: 'Save' }, fields: Array, initial: { type: Object, default: () => ({}) }, save: Function })
const emit = defineEmits(['update:modelValue', 'saved'])
const open = ref(props.modelValue)
const values = reactive({})
const busy = ref(false)
watch(() => props.modelValue, (v) => {
  open.value = v
  if (v) {
    for (const k of Object.keys(values)) delete values[k]
    Object.assign(values, props.initial)
  }
}, { immediate: true })
watch(open, (v) => emit('update:modelValue', v))

async function submit() {
  for (const fld of props.fields) {
    if (fld.required && (values[fld.name] === undefined || values[fld.name] === '' || values[fld.name] === null)) {
      toast.error(`${fld.label} is needed.`)
      return
    }
  }
  busy.value = true
  try {
    const out = await props.save({ ...values })
    open.value = false
    emit('saved', out)
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.value = false
  }
}
</script>
