<template>
  <Dialog v-model:open="open" :title="title" size="md" :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: action, variant: 'solid', onClick: submit }]">
    <div class="flex flex-col gap-3">
      <template v-for="fld in fields" :key="fld.name">
        <LifeLink v-if="fld.link" v-model="values[fld.name]" :doctype="fld.link" :filters="fld.filters" :label="fld.label" :required="fld.required" :placeholder="fld.placeholder" />
        <FormControl v-else-if="fld.options" v-model="values[fld.name]" type="select" :label="fld.label" :required="fld.required" :description="fld.help"
          :placeholder="fld.placeholder || 'Choose'" :options="options(fld)" />
        <FormControl v-else-if="fld.type === 'textarea'" v-model="values[fld.name]" type="textarea" :label="fld.label" :required="fld.required" :description="fld.help" :rows="3" />
        <DatePicker format="D MMM YYYY" v-else-if="fld.type === 'date'" v-model="values[fld.name]" :label="fld.label" :required="fld.required" :description="fld.help" />
        <FormControl v-else v-model="values[fld.name]" :type="fld.type || 'text'" :label="fld.label" :required="fld.required" :description="fld.help" :maxlength="fld.maxlength"
          :placeholder="fld.placeholder" @keydown.enter="submit()" />
      </template>
    </div>
  </Dialog>
</template>
<script setup>
// A small form dialog used for "New goal", "New note", "Add event" and the like. Every control is a library control:
// frappe-ui FormControl and DatePicker, and @framework/ui's Link (through LifeLink) for a field that points to a record.
// A field is { name, label, required, help, placeholder } plus one of: options (a select), type ('textarea', 'date', 'number'), link (a DocType).
import { reactive, ref, watch } from 'vue'
import { DatePicker, Dialog, FormControl, toast } from 'frappe-ui'
import LifeLink from '@/framework/LifeLink.vue'
import { errorText } from '@/lib/api'

const props = defineProps({ modelValue: Boolean, title: String, action: { type: String, default: 'Save' }, fields: Array, initial: { type: Object, default: () => ({}) }, save: Function })
const emit = defineEmits(['update:modelValue', 'saved'])
const open = ref(props.modelValue)
const values = reactive({})
const busy = ref(false)
const options = (fld) => fld.options.map((o) => (typeof o === 'object' ? { label: o.label, value: o.value } : { label: String(o), value: o }))
watch(() => props.modelValue, (v) => {
  open.value = v
  if (v) {
    for (const k of Object.keys(values)) delete values[k]
    Object.assign(values, props.initial)
  }
}, { immediate: true })
watch(open, (v) => emit('update:modelValue', v))

async function submit() {
  if (busy.value) return
  for (const fld of props.fields) {
    if (fld.required && (values[fld.name] === undefined || values[fld.name] === '' || values[fld.name] === null)) {
      toast.error(`${fld.label} is needed.`)
      return
    }
  }
  busy.value = true
  try {
    const clean = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v === null ? undefined : v]))
    const out = await props.save(clean)
    open.value = false
    emit('saved', out)
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.value = false
  }
}
</script>
