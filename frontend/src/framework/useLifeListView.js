// The one place a list gets its state from @framework/ui: filters, sort, columns, quick-filter fields and group by.
// Screens never import @framework/ui; they use ListView.vue, which uses this.
import { computed } from 'vue'
import { useListView } from '@framework/ui/ListView'
import { getFilterableFields, parseFilters } from '@framework/ui/Filter'
import { parseOrderBy } from '@framework/ui/SortBy'
import { serializeGroupBy } from '@framework/ui/GroupBy'
import { useDoctypeMeta } from '@framework/ui/composables/useDoctypeMeta.ts'

// standard fields the library offers that our list methods do not filter on, and the space, which the screen fixes
const NOT_OFFERED = new Set(['_user_tags', '_liked_by', '_assign', 'space'])

/**
 * @param doctype  the DocType whose fields the controls offer ('Life Task', or 'Life Index' for the cross-type lists)
 * @param options.virtual    filter fields declared by the screen: [{ fieldname, label, fieldtype, options }]. One with a new name is resolved
 *                           by the server from a short URL parameter (a tag). One with the name of a real field replaces how that field
 *                           is offered: on Life Index, `area` is stored as text, and declaring it a Link gives it the record picker.
 * @param options.synthetic  table columns the screen draws itself: [{ key: '_badge', label, width, align, place }]
 * @param options.hidden     field names not to offer in the filter
 * @param options.only       when given, the only real fields offered (a list whose method filters on a few fields, not on every one)
 */
export function useLifeListView(doctype, { virtual = [], synthetic = [], hidden = [], only = null } = {}) {
  const view = useListView(doctype, { synthetic })
  const { meta } = useDoctypeMeta(doctype)
  const metaFields = computed(() => meta.value?.fields ?? [])
  const ready = computed(() => !!meta.value)

  // every field a condition can be made on, as the Filter control wants them
  const fields = computed(() => [
    ...getFilterableFields(metaFields.value, doctype).filter((f) => !NOT_OFFERED.has(f.fieldname) && !hidden.includes(f.fieldname) && (!only || only.includes(f.fieldname)) && !virtual.some((v) => v.fieldname === f.fieldname)),
    ...virtual.map((v) => ({ ...v, value: v.fieldname })),
  ])
  // the same list in the shape of the Filter's `fields` prop: a name for a Meta field, a declaration for a virtual one
  const filterFields = computed(() => fields.value.map((f) => (virtual.some((v) => v.fieldname === f.fieldname) ? { fieldname: f.fieldname, label: f.label, fieldtype: f.fieldtype, options: f.options } : f.fieldname)))
  const field = (name) => fields.value.find((f) => f.fieldname === name)

  const wire = view.filters.wire
  const orderBy = view.sort.orderBy
  const setWire = (list) => { view.filters.conditions.value = parseFilters(fields.value, list) }
  const setOrderBy = (text) => { view.sort.by.value = parseOrderBy(text || '') }
  const setQuickFields = (names) => { view.quickFilter.fields.value = names.map(field).filter(Boolean) }

  // the grouped request for our list methods' `summary` argument, or null when the list is not grouped
  const summary = computed(() => {
    const g = view.groupBy.value
    if (!g || !g.fields?.length) return null
    return { fields: g.fields, aggregates: g.aggregates, order_by: serializeGroupBy(g).order_by, totals: g.showTotals ? 1 : 0 }
  })
  // what is saved with a view, on top of its URL: plain JSON
  const layout = computed(() => ({
    columns: view.columns.isCustomized.value ? view.columns.shown.value : null,
    quick: view.quickFilter.fields.value.map((f) => f.fieldname),
    groupBy: view.groupBy.value,
  }))
  function restoreLayout(saved = {}) {
    if (Array.isArray(saved.columns) && saved.columns.length) view.columns.shown.value = saved.columns
    if (saved.groupBy !== undefined) view.groupBy.value = saved.groupBy || null
  }
  const fieldMeta = (name) => metaFields.value.find((f) => f.fieldname === name)

  return { doctype, view, ready, fields, filterFields, field, fieldMeta, wire, orderBy, setWire, setOrderBy, setQuickFields, summary, layout, restoreLayout, synthetic }
}
