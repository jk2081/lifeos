<template>
  <Dropdown :options="[{ label: showHidden ? 'Hide hidden events' : 'Show hidden events', icon: showHidden ? 'lucide-eye-off' : 'lucide-eye', onClick: () => (showHidden = !showHidden) }]" placement="right">
    <Button icon="lucide-ellipsis" label="Week menu" tooltip="Week menu" data-week-menu />
  </Dropdown>
</template>
<script setup>
// The week's menu (issue 99): Show hidden events brings back the events that were hidden in Life OS.
import { Button, Dropdown } from 'frappe-ui'
import { showHidden } from '@/lib/calRange'
</script>
