<template>
  <div class="flex min-h-12 flex-wrap items-center gap-2.5 border-b border-outline-gray-1 py-2 last:border-b-0" :data-member="member.user" :data-kind="member.kind">
    <Avatar size="md" :label="member.full_name" :image="member.image" />
    <div class="min-w-0 flex-1 basis-40">
      <div class="break-words text-base-medium text-ink-gray-9">{{ member.full_name }}</div>
      <div class="break-all text-sm text-ink-gray-6">{{ member.user }}</div>
    </div>
    <Badge :theme="KIND_THEME[member.kind] || 'gray'" :label="member.kind" :data-kind-badge="member.kind" :data-owner-badge="member.is_owner || undefined" />
    <span v-if="member.is_owner" class="w-32 text-sm text-ink-gray-7">Can edit</span>
    <Select v-else class="w-32" :model-value="member.access" :options="ACCESS" :disabled="!writable" :aria-label="`Access for ${member.full_name}`" :data-access="member.user"
      @update:model-value="(v) => v !== member.access && emit('access', v)" />
    <Dropdown v-if="!member.is_owner && writable" :options="[{ label: 'Remove', icon: 'lucide-user-minus', theme: 'red', onClick: () => emit('remove') }]">
      <Button variant="ghost" icon="lucide-ellipsis" :label="`More for ${member.full_name}`" :data-member-menu="member.user" />
    </Dropdown>
    <span v-else class="size-7 flex-none max-md:hidden" aria-hidden="true" />
  </div>
</template>
<script setup>
// One member of a space, a person or an agent (issue 1): avatar, name, email, a kind badge (Owner, Person, Agent),
// access (the owner always has Can edit) and Remove. Settings > People and agents > Members lists these.
import { Avatar, Badge, Button, Dropdown, Select } from 'frappe-ui'

defineProps({ member: { type: Object, required: true }, writable: { type: Boolean, default: true } })
const emit = defineEmits(['access', 'remove'])
const ACCESS = [{ label: 'Can view', value: 'Read' }, { label: 'Can edit', value: 'Write' }]
const KIND_THEME = { Owner: 'green', Person: 'gray', Agent: 'blue' }
</script>
