<template>
  <PageHead :title="person?.title || 'Person'" :crumb="{ label: 'People', to: '/library/people', here: person?.title || '...' }">
    <Button v-if="person" label="All people" icon-left="lucide-arrow-left" data-person-back @click="router.push({ path: '/library/people', query: { space: route.query.space } })" />
  </PageHead>
  <div class="page-body max-w-6xl" data-library-person :data-loaded="person ? 1 : 0" :data-kind="person?.kind">
    <Card v-if="missing" class="py-2" data-person-missing><Empty title="Not found." hint="This person or organisation is gone, or is not in a space you can see." /></Card>
    <div v-else-if="person" class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]" data-person-grid>
      <div class="flex min-w-0 flex-col gap-4">
        <Card data-person-who>
          <h2 class="mb-2 text-base-medium text-ink-gray-9">Who {{ person.kind === 'Organisation' ? 'they are' : 'this is' }}</h2>
          <Md v-if="person.text" :text="person.text" data-person-text />
          <p v-else class="text-base text-ink-gray-6" data-person-no-text>Nothing written yet. When the Brain files something about {{ person.title }}, it will appear here.</p>
          <p v-if="person.wiki" class="mt-2 text-sm text-ink-gray-6">From the wiki page <a class="text-ink-blue-8 hover:underline" href="#" data-person-wiki @click.prevent="openRef('note:' + person.wiki.name)">{{ person.wiki.title }}</a></p>
        </Card>
        <Card class="!p-0" data-person-mentions>
          <h2 class="px-4 pt-3 text-base-medium text-ink-gray-9">Mentioned in <span class="text-sm text-ink-gray-6" data-mention-count>{{ person.mentioned_total }}</span></h2>
          <ul v-if="person.mentioned.length" class="mt-2 flex flex-col">
            <li v-for="m in person.mentioned" :key="m.ref" class="border-t border-outline-gray-1 hover:bg-surface-gray-1" data-mention :data-ref="m.ref" :data-kind="m.kind">
              <button type="button" class="flex w-full min-w-0 items-baseline gap-3 px-4 py-2.5 text-left focus-visible:focus-ring" @click="openRef(m.ref)">
                <Badge class="flex-none" size="sm" :label="m.kind" />
                <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9" data-mention-title>{{ m.title }}<span v-if="m.how" class="text-sm text-ink-gray-6"> · {{ m.how }}</span></span>
                <span class="flex-none whitespace-nowrap text-sm text-ink-gray-6" data-mention-date>{{ short(m.date) }}</span>
              </button>
            </li>
          </ul>
          <p v-else class="px-4 pb-3 pt-1 text-sm text-ink-gray-6" data-mention-empty>Nothing mentions {{ person.title }} yet. Captures, notes, tasks, meetings and chats that name them will show up here.</p>
        </Card>
      </div>
      <div class="flex min-w-0 flex-col gap-4">
        <Card data-person-facts>
          <div class="flex flex-wrap items-center gap-2"><Badge size="lg" :label="person.kind" data-person-kind /><span v-if="person.role" class="text-base text-ink-gray-8" data-person-role>{{ person.role }}</span></div>
          <dl class="mt-3 flex flex-col gap-2 text-sm">
            <div v-if="person.organisation"><dt class="text-ink-gray-6">Organisation</dt>
              <dd><a class="text-base text-ink-blue-8 hover:underline" :href="'/life/library/people/' + person.organisation.name" data-person-org @click.prevent="go(person.organisation.name)">{{ person.organisation.title || person.organisation.full_name }}</a></dd></div>
            <div v-if="person.area_name"><dt class="text-ink-gray-6">Area</dt><dd class="text-base text-ink-gray-8">{{ person.area_name }}</dd></div>
            <div v-if="person.aliases.length"><dt class="text-ink-gray-6">Also called</dt><dd class="text-base text-ink-gray-8">{{ person.aliases.join(', ') }}</dd></div>
          </dl>
        </Card>
        <Card v-if="person.kind === 'Organisation'" data-person-people>
          <h2 class="mb-2 text-base-medium text-ink-gray-9">People</h2>
          <ul v-if="person.people.length" class="flex flex-col gap-1">
            <li v-for="m in person.people" :key="m.name" data-org-person :data-name="m.name">
              <a class="block rounded px-1 py-1 hover:bg-surface-gray-1" :href="'/life/library/people/' + m.name" @click.prevent="go(m.name)">
                <span class="text-base text-ink-blue-8">{{ m.title }}</span><span v-if="m.role" class="text-sm text-ink-gray-6"> · {{ m.role }}</span></a>
            </li>
          </ul>
          <p v-else class="text-sm text-ink-gray-6" data-org-no-people>No one is linked to {{ person.title }} yet.</p>
        </Card>
      </div>
    </div>
  </div>
</template>
<script setup>
// A person's or organisation's page (issue 25): who they are (the linked wiki page's text), their organisation or its people, and
// Mentioned in: captures, notes, tasks, meetings and chats, newest first. One column on a phone; the facts sit beside it from 1024 px.
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import Md from '@/components/Md.vue'
import PageHead from '@/components/PageHead.vue'
import { api } from '@/lib/api'
import { short } from '@/lib/dates'
import { onRecordChanged, openRef } from '@/lib/pane'

const props = defineProps({ person: String })
const route = useRoute()
const router = useRouter()
const person = ref(null)
const missing = ref(false)
const go = (name) => router.push({ path: `/library/people/${name}`, query: { space: route.query.space } })

async function load() {
  try {
    person.value = await api('people.get', { name: props.person })
    missing.value = false
  } catch (e) {
    person.value = null
    missing.value = true
  }
}
watch(() => props.person, load)
onRecordChanged(load)
onMounted(load)
</script>
