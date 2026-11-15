<template>
  <ListView ref="list" title="Vault" noun="documents" :filters="FILTERS" :columns="COLUMNS" :fetch="fetch" :row-ref="(r) => 'vault:' + r.name"
    default-sort="soonest expiry" empty-title="The vault is empty."
    empty-hint="Keep IDs, travel papers, insurance and tax documents here with their expiry dates. Add one, or drop a scan in the Inbox."
    @loaded="(res) => (counts = res)">
    <template #sub>
      <RouterLink class="num" :to="{ query: { expiry: 'expired' } }" data-door="vault-expired">{{ counts.expired }} expired</RouterLink> ·
      <RouterLink class="num" :to="{ query: { expiry: 'soon' } }" data-door="vault-soon">{{ counts.soon }} expiring within 60 days</RouterLink>
    </template>
    <template #actions><button v-if="canWrite()" class="bt p" type="button" @click="openRef('vault:new')">Add document</button></template>
    <template #cell-title="{ row }"><div class="ttl">{{ row.title }}</div></template>
    <template #cell-number="{ row }"><span style="font-variant-numeric: tabular-nums">{{ row.number_last4 ? '···· ' + row.number_last4 : '' }}</span></template>
    <template #cell-expiry_date="{ row }">{{ short(row.expiry_date, true) }}</template>
    <template #cell-badge="{ row }"><span v-if="row.badge" class="pl" :class="row.badge.state === 'expired' ? 'r' : 'o'">{{ badgeText(row.badge) }}</span>
      <span v-else-if="row.file" class="pl n">File</span></template>
    <template #stack="{ row }">
      <div style="display: flex; gap: 10px; align-items: flex-start">
        <div style="flex: 1; min-width: 0"><div class="ttl">{{ row.title }}</div>
          <div class="mt">{{ [row.doc_type, row.holder_name, row.expiry_date && 'expires ' + short(row.expiry_date, true)].filter(Boolean).join(' · ') }}</div></div>
        <span v-if="row.badge" class="pl" :class="row.badge.state === 'expired' ? 'r' : 'o'">{{ row.badge.state === 'expired' ? 'Expired' : `${row.badge.days} days` }}</span>
      </div>
    </template>
    <template #below><p class="mt" style="margin: 0">Only the last four characters of any number are stored. Files are private to this space.</p></template>
  </ListView>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import ListView from '@/components/ListView.vue'
import { api } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { VAULT_TYPES } from '@/lib/tasks'
import { areaOptions, loadLookups, lookups } from '@/lib/lookups'
import { openRef } from '@/lib/pane'

const list = ref(null)
const counts = ref({ expired: 0, soon: 0 })
const FILTERS = computed(() => [
  { key: 'holder', label: 'Holder', all: 'Any holder', options: [...(lookups.people || []).map((p) => ({ value: p.name, label: p.full_name })), { value: 'none', label: 'No holder' }] },
  { key: 'type', label: 'Type', all: 'Any type', options: VAULT_TYPES.map((t) => ({ value: t, label: t })) },
  { key: 'expiry', label: 'Expiry', all: 'Any expiry', options: [{ value: 'expired', label: 'Expired' }, { value: 'soon', label: 'Within 60 days' },
    { value: 'later', label: 'Later' }, { value: 'none', label: 'No expiry date' }] },
  { key: 'area', label: 'Area', all: 'All areas', quiet: true, options: areaOptions() },
  { key: 'project', label: 'Project', all: 'All projects', quiet: true, options: lookups.projects.map((p) => ({ value: p.name, label: p.title })) },
  { key: 'archived', label: 'Include archived', type: 'check', quiet: true },
])
const COLUMNS = [{ key: 'title', label: 'Document', width: 'minmax(180px, 2fr)', sort: 'title' }, { key: 'doc_type', label: 'Type', sort: 'doc_type' },
  { key: 'holder_name', label: 'Holder', sort: 'holder' }, { key: 'number', label: 'Number', width: '90px' },
  { key: 'expiry_date', label: 'Expires', sort: 'expiry_date', nowrap: true }, { key: 'area_name', label: 'Area' }, { key: 'badge', label: '', width: '130px', align: 'right' }]
const badgeText = (b) => (b.state === 'expired' ? 'Expired' : b.days === 0 ? 'Expires today' : `Expires in ${b.days} days`)
async function fetch({ filters: f, sort, dir, start, page_length }) {
  const res = await api('vault.list', { space: store.space, holder: f.holder || undefined, doc_type: f.type || undefined, expiry: f.expiry || undefined,
    area: f.area || undefined, project: f.project || undefined, include_archived: f.archived ? 1 : 0, sort: sort || undefined, dir: dir || undefined, start, page_length })
  return { rows: res.documents, total: res.total, expired: res.expired, soon: res.soon }
}
onMounted(loadLookups)
</script>
