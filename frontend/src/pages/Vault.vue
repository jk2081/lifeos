<template>
  <ListView ref="list" title="Vault" noun="documents" screen="vault" doctype="Life Vault Document" :spec="SPEC" :tabs="TABS" :flag-labels="{ archived: 'Include archived' }" :quiet="['archived']"
    :quick="['doc_type', 'holder', 'area']" :synthetic="SYNTHETIC" :fetch="fetch" :row-ref="(r) => 'vault:' + r.name" empty-title="The vault is empty."
    empty-hint="Keep IDs, travel papers, insurance and tax documents here with their expiry dates. Add one, or drop a scan in the Inbox."
    @loaded="(res) => (counts = res)">
    <template #sub>
      <NumLink :to="{ query: { expiry: 'expired' } }" data-door="vault-expired">{{ counts.expired }} expired</NumLink> ·
      <NumLink :to="{ query: { expiry: 'soon' } }" data-door="vault-soon">{{ counts.soon }} expiring within 60 days</NumLink>
    </template>
    <template #actions><Button v-if="canWrite()" variant="solid" icon-left="lucide-plus" label="Add document" @click="openRef('vault:new')" /></template>
    <template #cell-title="{ row }"><span class="break-words font-medium text-ink-gray-9">{{ row.title }}</span></template>
    <template #cell-holder="{ row }"><span class="truncate">{{ row.holder_name }}</span></template>
    <template #cell-number_last4="{ row }"><span class="tabular-nums">{{ row.number_last4 ? '···· ' + row.number_last4 : '' }}</span></template>
    <template #cell-_badge="{ row }"><Badge v-if="row.badge" :theme="row.badge.state === 'expired' ? 'red' : 'amber'" :label="badgeText(row.badge)" />
      <Badge v-else-if="row.file" label="File" /></template>
    <template #stack="{ row }">
      <div class="flex items-start gap-2.5">
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ row.title }}</div>
          <div class="text-sm text-ink-gray-6">{{ [row.doc_type, row.holder_name, row.expiry_date && 'expires ' + short(row.expiry_date, true)].filter(Boolean).join(' · ') }}</div></div>
        <Badge v-if="row.badge" :theme="row.badge.state === 'expired' ? 'red' : 'amber'" :label="row.badge.state === 'expired' ? 'Expired' : `${row.badge.days} days`" />
      </div>
    </template>
    <template #below><p class="text-sm text-ink-gray-6">Only the last four characters of any number are stored. Files are private to this space.</p></template>
  </ListView>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import NumLink from '@/components/ui/NumLink.vue'
import { api } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { loadLookups } from '@/lib/lookups'
import { openRef } from '@/lib/pane'
import { EXPIRY_PRESETS } from '@/lib/filterUrl'

const list = ref(null)
const counts = ref({ expired: 0, soon: 0 })
const SPEC = [
  { key: 'holder', field: 'holder', kind: 'link' }, { key: 'type', field: 'doc_type', kind: 'value', label: 'Type' },
  { key: 'expiry', field: 'expiry_date', kind: 'preset', label: 'Expiry', presets: EXPIRY_PRESETS, labels: { expired: 'Expired', soon: 'Within 60 days', later: 'Later', none: 'No expiry date' } },
  { key: 'area', field: 'area', kind: 'link' }, { key: 'project', field: 'project', kind: 'link' }, { key: 'archived', kind: 'flag' },
]
// the state tabs, on expiry=. All is the default; "Expiring soon" is the 60-day window of the expiry filter
const TABS = { key: 'expiry', field: 'expiry_date', label: 'Expiry', items: [{ value: 'all', label: 'All' }, { value: 'soon', label: 'Expiring soon' }, { value: 'expired', label: 'Expired' }] }
const SYNTHETIC = [{ key: '_badge', label: '', width: '9rem', align: 'right', place: 'end' }]
const badgeText = (b) => (b.state === 'expired' ? 'Expired' : b.days === 0 ? 'Expires today' : `Expires in ${b.days} days`)
async function fetch({ params: p, tab, filters, order_by, fields, summary, start, page_length }) {
  const res = await api('vault.list', { space: store.space, holder: p.holder, doc_type: p.type, expiry: tab === 'all' ? p.expiry : tab, area: p.area, project: p.project,
    include_archived: p.archived ? 1 : 0, filters, order_by, fields, summary, start, page_length })
  return summary ? res : { rows: res.documents, total: res.total, expired: res.expired, soon: res.soon, tabs: res.tabs }
}
onMounted(loadLookups)
</script>
