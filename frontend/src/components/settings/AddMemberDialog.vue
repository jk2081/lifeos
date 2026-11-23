<template>
  <Dialog v-model:open="open" :title="`Add a member to ${space}`" size="sm"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Add', variant: 'solid', disabled: !canAdd, onClick: add }]">
    <div class="flex flex-col gap-3" data-add-dialog>
      <Combobox v-model="user" v-model:query="query" :options="options" :filterable="false" :loading="loading" label="Person or agent"
        placeholder="Search by name or email" open-on-focus open-on-click data-add-search @update:open="(o) => o && !user && (query = '')" />
      <div v-if="picked" class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-7" data-add-picked :data-kind="picked.kind || 'none'">
        <Badge :theme="picked.kind === 'Agent' ? 'blue' : 'gray'" :label="picked.kind || 'No Life OS access yet'" />
        <span class="break-all">{{ picked.name }}</span>
      </div>
      <template v-if="picked && !picked.kind">
        <p class="text-sm text-ink-gray-7" data-add-no-role>{{ picked.full_name }} has no Life OS access yet. Say what they are, and Add gives them that access.</p>
        <TabButtons v-model="role" :options="ROLES" aria-label="Kind" data-add-role />
      </template>
      <Select v-model="access" :options="ACCESS" aria-label="Access" data-add-access />
      <p v-if="kind === 'Agent'" class="text-sm text-ink-gray-6" data-add-agent-note>Agents need Can edit to file captures and proposals.</p>
    </div>
  </Dialog>
</template>
<script setup>
// Add member (issue 1): searches every user, people and agents alike (settings.find_users), and shows each one's kind.
// Access defaults to Can edit for a person and Can view for an agent. A user with no Life OS access is offered the access
// that fits (a person or an agent), given only when the owner presses Add.
import { settingsData } from '@/data/settings'
import { computed, ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { Badge, Combobox, Dialog, Select, TabButtons } from 'frappe-ui'
import { tryCall } from '@/lib/api'

const props = defineProps({ space: { type: String, required: true } })
const open = defineModel('open', { type: Boolean, default: false })
const emit = defineEmits(['added'])
const ACCESS = [{ label: 'Can view', value: 'Read' }, { label: 'Can edit', value: 'Write' }]
const ROLES = [{ label: 'A person', value: 'Person' }, { label: 'An agent', value: 'Agent' }]
const GRANT = { Person: 'Life User', Agent: 'Life Agent' }

const user = ref(null)
const query = ref('')
const found = ref([])
const loading = ref(false)
const role = ref('')
const access = ref('Write')
const picked = computed(() => found.value.find((r) => r.name === user.value) || null)
const kind = computed(() => picked.value?.kind || role.value || null)
const canAdd = computed(() => !!picked.value && !picked.value.is_member && !!kind.value)
const options = computed(() => found.value.map((r) => ({ label: r.full_name, value: r.name, disabled: r.is_member,
  description: `${r.name} · ${r.is_member ? 'already in ' + props.space : r.kind || 'no Life OS access yet'}` })))

let asked = 0
// one search per pause in typing, and only the newest answer is kept
const search = useDebounceFn(async (q) => {
  const id = ++asked
  loading.value = true
  const rows = await tryCall(() => settingsData.settings.find_users({ txt: q || '', space: props.space }))
  if (id !== asked) return
  loading.value = false
  // keep the chosen user among the options, so the field still shows its name
  found.value = [...(picked.value && !(rows || []).some((r) => r.name === picked.value.name) ? [picked.value] : []), ...(rows || [])]
}, 200)
watch(query, (q) => { if (!(picked.value && q === picked.value.full_name)) search(q) })
watch(kind, (k) => { access.value = k === 'Agent' ? 'Read' : 'Write' })
watch(open, (o) => {
  if (!o) return
  user.value = null
  role.value = ''
  access.value = 'Write'
  query.value = ''
  found.value = []
  asked++
  tryCall(() => settingsData.settings.find_users({ txt: '', space: props.space })).then((rows) => { if (!user.value) found.value = rows || [] })
})

async function add({ close } = {}) {
  if (!canAdd.value) return
  const grant = picked.value.kind ? undefined : GRANT[role.value]
  const res = await tryCall(() => settingsData.settings.set_member({ space: props.space, user: user.value, access: access.value, grant_role: grant }), 'Added')
  if (!res) return
  emit('added', res)
  close ? close() : (open.value = false)
}
</script>
