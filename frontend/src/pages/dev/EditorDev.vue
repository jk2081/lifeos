<template>
  <PageHead title="Editor (development)">
    <template #sub>A sample note with every element the editor draws. Nothing on this page is saved.</template>
    <Dropdown :options="menu"><Button icon="lucide-ellipsis" label="More" data-note-menu /></Dropdown>
  </PageHead>
  <div class="page-body" data-dev-editor>
    <Card v-if="!store.isAdmin"><EmptyState line="Only the owner can open this page. It is for checking the editor during development." /></Card>
    <template v-else>
      <LiveEditor v-model="text" :space="store.space" :links="links" :raw="raw" label="Sample note" />
      <div class="text-sm text-ink-gray-6" data-dev-length>{{ text.length }} characters</div>
    </template>
  </div>
</template>
<script setup>
// /life/dev/editor: the editor on a sample note, for the screenshot check of UX fixes set 4 before it replaced the old one.
// Owner only, not in the sidebar. Pasted images upload as private files attached to nothing.
import { computed, ref } from 'vue'
import { Button, Dropdown } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import LiveEditor from '@/components/LiveEditor.vue'
import Card from '@/components/ui/Card.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { store } from '@/lib/store'

const raw = ref(false)
const menu = computed(() => [{ label: raw.value ? 'Show formatted' : 'Show Markdown', icon: 'lucide-code', onClick: () => { raw.value = !raw.value } }])
const links = [{ text: 'Dalmia Gold blend blueprint', name: 'sample', title: 'Dalmia Gold blend blueprint', route: '/library' }]
const text = ref(`# Estate visit, November

A note to try the editor. **Bold**, *italic*, ~~struck~~ and \`inline code\` render as you type.
The marks show only on the line with the cursor.

## Plans for the week

- Walk the lower division with the manager
- Check the nursery stock
    - count by clone
- Send the [blend sheet](https://example.com/blend) to Mithun

1. Morning: field visit
2. Afternoon: factory

### Checklist

- [x] Book the car
- [ ] Ask for the soil report
- [ ] Read [[Dalmia Gold blend blueprint]] and [[A page that does not exist yet]]

> The best time to plant a tea bush was twenty years ago.

---

| Garden | Yield (kg/ha) | Note |
| --- | --- | --- |
| Ghatia | 2,150 | after pruning |
| Ghillidary | 1,870 | drainage work |

![A sample picture](/assets/lifeos/icons/icon-192.png)

\`\`\`
plain code block
\`\`\`
`)
</script>
