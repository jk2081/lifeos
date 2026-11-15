<template>
  <FileUploader :doctype="doctype" :docname="docname" :fieldname="fieldname" :file-types="accept || undefined" :private="true"
    @success="(doc) => $emit('uploaded', doc)" @failure="(e) => toast.error(errorText(e))">
    <template #default="{ openFileSelector, uploading, progress, error }">
      <Button :label="uploading ? `Uploading ${progress}%` : label" icon-left="lucide-paperclip" :disabled="disabled" :loading="uploading" data-file-upload @click="openFileSelector" />
      <ErrorMessage v-if="error" class="mt-1" :message="error" />
    </template>
  </FileUploader>
</template>
<script setup>
// Attach one file to a record. frappe-ui's FileUploader stores it PRIVATE, attached to `doctype` / `docname` (and `fieldname`,
// when the file belongs to one field). `uploaded` carries the File document the server made.
import { Button, ErrorMessage, FileUploader, toast } from 'frappe-ui'
import { errorText } from '@/lib/api'
defineProps({ doctype: String, docname: String, fieldname: String, accept: { type: [String, Array], default: '' }, disabled: Boolean,
  label: { type: String, default: 'Attach a file' } })
defineEmits(['uploaded'])
</script>
