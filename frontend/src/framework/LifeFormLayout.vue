<template>
  <FormLayout v-if="layout" :layout="layout" :doc="values" />
</template>
<script setup>
// Fields of a DocType drawn as a form, from the DocType's own meta: each field gets the control of its fieldtype, its label,
// its options and its Link target. Wraps @framework/ui FormLayout.
//   values     a reactive object the fields read and write in place (pass a `reactive({})`); nothing is saved here:
//              the screen saves through its own lifeos.api method
//   rows       field names, one list per row: [['title'], ['doc_type', 'holder', 'number_last4']]
//   overrides  per field name, what the screen changes: { label, description, placeholder, filters, reqd, props }
//              (`props` are bound onto the control, for example { maxlength: 4 })
//   titles     what a Link value shows before its options load: { 'Life Person::PER-0001': 'Asha' }
//   disabled   every field read-only
// `change` fires with (fieldname, value) when a field is committed: blur for typed fields, a pick for the others.
import { computed, provide } from 'vue'
import { CommitKey, FormLayout, LinkTitlesKey, buildLayoutFromMeta } from '@framework/ui/FormLayout'
import { useDoctypeMeta } from '@framework/ui/composables/useDoctypeMeta.ts'

const props = defineProps({
  doctype: { type: String, required: true },
  values: { type: Object, required: true },
  rows: { type: Array, required: true },
  overrides: { type: Object, default: () => ({}) },
  titles: { type: Object, default: () => ({}) },
  disabled: Boolean,
})
const emit = defineEmits(['change'])
const { meta } = useDoctypeMeta(() => props.doctype)

// the library's own mapping of one DocField, so a field here is exactly what a full form would show
const node = (raw) => buildLayoutFromMeta([raw])[0].sections[0].columns[0].fields[0]
const layout = computed(() => {
  const fields = meta.value?.fields
  if (!fields) return null
  const sections = props.rows.map((row) => ({
    hideLabel: true, hideBorder: true,
    columns: row.map((name) => fields.find((f) => f.fieldname === name)).filter(Boolean).map((raw) => {
      const { props: controlProps, ...over } = props.overrides[raw.fieldname] || {}
      const field = { ...node(raw), ...over }
      if (controlProps) field.ui = { props: controlProps }
      if (props.disabled) field.readOnly = true
      return { fields: [field] }
    }),
  }))
  return [{ sections }]
})

provide(CommitKey, { pending: () => {}, commit: (fieldname, value) => emit('change', fieldname, value), rowChanged: () => {} })
provide(LinkTitlesKey, computed(() => props.titles))
</script>
