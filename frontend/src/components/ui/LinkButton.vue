<template>
  <Button variant="ghost" class="!h-auto !min-w-0 !justify-start !whitespace-normal break-words !px-0 !py-0 text-left hover:!bg-transparent hover:underline"><slot /></Button>
</template>
<script setup>
// A control that reads as a link: a title that opens a record, an example to tap. It is frappe-ui's ghost Button with the box taken off, so it keeps the
// library's focus ring and dark-mode colours; size and weight come from the classes you give it.
import { Button } from 'frappe-ui'
</script>
