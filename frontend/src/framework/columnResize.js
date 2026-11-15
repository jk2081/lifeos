// Drag-resize of a table header cell, written into the same columns ColumnSettings edits.
// Wraps the resize composable of @framework/ui's experimental List.
import { useColumnResize } from '@framework/ui/experimental/List/useColumnResize.ts'
import { directionFor, nextSort } from '@framework/ui/experimental/List'

export function useLifeColumnResize(list) {
  return useColumnResize({
    onResize: (fieldname, width) => list.view.columns.setWidth(fieldname, width),
    onReset: (fieldname) => list.view.columns.resetWidth(fieldname),
  })
}
export { directionFor, nextSort }
