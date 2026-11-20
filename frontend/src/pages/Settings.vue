<template>
  <PageHead title="Settings" :sub="store.fullName || store.user" />
  <div class="flex min-h-0 flex-1 max-md:block" data-settings>
    <!-- the menu: three groups. On a phone it is the first screen and a section opens full width with Back. -->
    <nav v-if="!phone || !section" class="w-60 flex-none overflow-y-auto border-r border-outline-gray-1 px-3 pb-10 pt-4 max-md:w-auto max-md:border-r-0 max-md:p-4" aria-label="Settings sections" data-settings-menu>
      <!-- wide screens: frappe-ui Tabs in its vertical form; a phone: the same groups as a list of rows, the first screen -->
      <Tabs v-if="!phone && d" vertical :model-value="section" @update:model-value="open">
        <TabList variant="ghost" class="w-full">
          <template v-for="g in groups" :key="g.key">
            <div class="px-2 pb-1 pt-4 text-sm-medium text-ink-gray-6 first:pt-0" :data-settings-group="g.key">{{ g.key === 'space' ? `${g.label} · ${spaceSel}` : g.label }}</div>
            <div v-if="g.key === 'space' && d" class="mb-1.5 px-1" @keydown.stop>
              <Select :model-value="spaceSel" :options="d.spaces.map((s) => ({ label: s.name, value: s.name }))" aria-label="Space for these settings" data-settings-space
                @update:model-value="pickSpace" />
            </div>
            <TabTrigger v-for="it in g.items" :key="it.value" class="w-full justify-start" :value="it.value" :label="it.label" :data-section="it.value" />
          </template>
        </TabList>
      </Tabs>
      <template v-else>
        <section v-for="g in groups" :key="g.key" class="mb-4 flex flex-col gap-0.5">
          <div class="mb-1 text-sm-medium text-ink-gray-6" :data-settings-group="g.key">{{ g.label }}</div>
          <div v-if="g.key === 'space' && d" class="mb-1.5">
            <Select :model-value="spaceSel" :options="d.spaces.map((s) => ({ label: s.name, value: s.name }))" aria-label="Space for these settings" data-settings-space
              @update:model-value="pickSpace" />
          </div>
          <Button v-for="it in g.items" :key="it.value" class="!justify-start" size="lg" variant="ghost" icon-right="lucide-chevron-right" :label="it.label" :data-section="it.value"
            @click="open(it.value)" />
        </section>
      </template>
    </nav>

    <section v-if="section && (!phone || section)" class="min-w-0 flex-1 overflow-y-auto px-7 pb-16 pt-6 max-md:p-4" data-settings-section :data-current="section">
      <div class="flex max-w-[720px] flex-col gap-4">
        <Button v-if="phone" class="-ml-2 self-start" variant="ghost" icon-left="lucide-arrow-left" label="Settings" data-settings-back @click="open('')" />
        <div class="flex items-center gap-3">
          <h2 class="min-w-0 flex-1 text-lg-semibold text-ink-gray-9" data-section-title>{{ heading }}</h2>
          <Button v-if="listOf(section) && section !== 'areas' && canEdit" variant="solid" icon-left="lucide-plus" :label="'New ' + listOf(section).one" data-new @click="newOpen = true" />
          <Button v-if="section === 'members' && memberSpace" variant="solid" icon-left="lucide-plus" label="Add member" data-add-member @click="addOpen = true" />
          <Button v-if="section === 'spaces'" label="New space" data-new-space @click="spaceOpen = true" />
        </div>
        <div v-if="!d" class="flex flex-col gap-3"><Skeleton v-for="i in 4" :key="i" class="h-10 w-full rounded-4" /></div>

        <!-- Me -->
        <Card v-else-if="section === 'appearance'" flush>
          <SettingRow label="Theme" help="Light, dark, or follow the system setting of this device.">
            <TabButtons :model-value="colorScheme" :options="SCHEMES" aria-label="Theme" data-theme-switch @update:model-value="setColorScheme" />
          </SettingRow>
        </Card>
        <Card v-else-if="section === 'profile'" flush data-settings-profile>
          <SettingRow label="Name" help="How Life OS greets you and labels what you write. It comes from your Frappe user.">
            <span class="text-base text-ink-gray-9">{{ store.fullName || store.user }}</span></SettingRow>
          <SettingRow label="Email" help="You sign in with this address."><span class="break-all text-base text-ink-gray-8">{{ store.user }}</span></SettingRow>
          <SettingRow label="Default space" help="The space the app opens in, and where new records go when no space is chosen." :error="errors.default_space">
            <Select class="w-44" :model-value="d.settings.default_space" :options="d.spaces.map((s) => s.name)" :disabled="!d.is_admin" data-setting="default_space"
              @update:model-value="(v) => setOne('default_space', v)" />
          </SettingRow>
          <p v-if="!d.is_admin" class="pb-3 text-sm text-ink-gray-6">Only the owner can change this.</p>
        </Card>
        <Card v-else-if="section === 'notifications'" flush data-settings-notifications>
          <SettingRow label="Reminders on Today" help="The weekly review, the month plan and the 12 Week cycle show as one line at the top of Today when they are due. Each has Skip.">
            <Badge theme="green" label="On" /></SettingRow>
          <SettingRow label="Email and phone" help="Life OS sends no email or push messages. Your agents may write to you in their own chats.">
            <Badge label="None" /></SettingRow>
          <p class="pb-3 text-sm text-ink-gray-6">When each rhythm happens is set under Your life, Rhythms.</p>
        </Card>
        <CalendarSection v-else-if="section === 'calendar'" />
        <template v-else-if="section === 'shortcuts'">
          <Card flush data-settings-shortcuts>
            <SettingRow v-for="g in GO" :key="g.key" :label="g.label" :help="'Press G, then ' + g.key.toUpperCase()"><KeyboardShortcut bg :combo="'G ' + g.key.toUpperCase()" /></SettingRow>
          </Card>
          <p class="text-sm text-ink-gray-6">Press ? anywhere for every shortcut, or Help at the foot of the sidebar.</p>
        </template>

        <!-- Your life: Rhythms -->
        <template v-else-if="section === 'rhythms'">
          <p class="text-sm text-ink-gray-6">When each rhythm happens. Today, Plan and the reminders follow these.</p>
          <SectionHead>Daily</SectionHead>
          <Card flush data-settings-rhythms>
            <SettingRow label="Start of day" help="When Today begins and the morning insights are ready." :error="errors.start_of_day">
              <TimePicker class="w-36" :model-value="hm(d.settings.start_of_day)" :disabled="!d.is_admin" data-setting="start_of_day" @update:model-value="(v) => setOne('start_of_day', v)" />
            </SettingRow>
          </Card>
          <SectionHead>Weekly</SectionHead>
          <Card flush>
            <SettingRow label="Weekly review" help="The day and time your review opens, starting with Reset." :error="errors.weekly_review_day || errors.weekly_review_time">
              <div class="flex flex-wrap gap-2">
                <Select class="w-36" :model-value="d.settings.weekly_review_day" :options="DAYS" :disabled="!d.is_admin" aria-label="Review day" data-setting="weekly_review_day"
                  @update:model-value="(v) => setOne('weekly_review_day', v)" />
                <TimePicker class="w-28" :model-value="d.settings.weekly_review_time" :disabled="!d.is_admin" aria-label="Review time" data-setting="weekly_review_time"
                  @update:model-value="(v) => setOne('weekly_review_time', v)" />
              </div>
            </SettingRow>
            <SettingRow label="Week starts on" help="Used for the week calendar." :error="errors.week_starts_on">
              <Select class="w-36" :model-value="d.settings.week_starts_on || 'Monday'" :options="['Monday', 'Sunday']" :disabled="!d.is_admin" data-setting="week_starts_on"
                @update:model-value="(v) => setOne('week_starts_on', v)" />
            </SettingRow>
          </Card>
          <SectionHead>Working hours</SectionHead>
          <Card flush data-settings-work-hours>
            <SettingRow label="Working days" help="The weekly review suggests times for goal work on these days only." :error="errors.work_days">
              <div class="flex flex-wrap gap-1.5" role="group" aria-label="Working days">
                <Button v-for="day in WEEKDAYS" :key="day" size="sm" :variant="workDays.includes(day) ? 'solid' : 'subtle'" :label="day.slice(0, 3)" :aria-label="day"
                  :aria-pressed="workDays.includes(day)" :disabled="!d.is_admin" :data-work-day="day" @click="toggleDay(day)" />
              </div>
            </SettingRow>
            <SettingRow label="Working day" help="When a working day starts and ends." :error="errors.work_start || errors.work_end">
              <div class="flex flex-wrap items-center gap-2">
                <TimePicker class="w-28" :model-value="hm(d.settings.work_start || '09:00')" :disabled="!d.is_admin" aria-label="Working day starts" data-setting="work_start"
                  @update:model-value="(v) => setOne('work_start', v)" />
                <span class="text-sm text-ink-gray-6">to</span>
                <TimePicker class="w-28" :model-value="hm(d.settings.work_end || '19:00')" :disabled="!d.is_admin" aria-label="Working day ends" data-setting="work_end"
                  @update:model-value="(v) => setOne('work_end', v)" />
              </div>
            </SettingRow>
          </Card>
          <SectionHead>Monthly</SectionHead>
          <Card flush>
            <SettingRow label="Month plan" help="Plan each month: Today reminds you in its first three days until the plan exists." :error="errors.month_plan_enabled">
              <TabButtons :model-value="d.settings.month_plan_enabled ? 1 : 0" :options="[{ label: 'On', value: 1 }, { label: 'Off', value: 0 }]" aria-label="Month plan"
                data-setting="month_plan_enabled" @update:model-value="(v) => d.is_admin && setOne('month_plan_enabled', v)" />
            </SettingRow>
          </Card>
          <SectionHead>12 Weeks</SectionHead>
          <Card flush>
            <SettingRow label="Current cycle" :help="d.cycle ? `Week ${d.cycle.week} of 12. The next cycle can be planned from week 11.` : 'No cycle is running. Start one on Plan, 12 Weeks.'">
              <span class="text-sm text-ink-gray-7" data-current-cycle>{{ d.cycle ? `${short(d.cycle.start_date)} to ${short(d.cycle.end_date, true)}` : '—' }}</span>
            </SettingRow>
            <SettingRow label="Score target" help="The weekly share of planned actions you aim to complete, in per cent." :error="errors.score_target">
              <TextInput class="w-28" type="number" min="1" max="100" :model-value="d.settings.score_target" :disabled="!d.is_admin" data-setting="score_target"
                @change="(e) => setOne('score_target', Number(e.target.value))"><template #suffix><span class="text-sm text-ink-gray-6">%</span></template></TextInput>
            </SettingRow>
            <SettingRow label="Break week" help="A week between cycles for review and planning." :error="errors.cycle_break_week">
              <TabButtons :model-value="d.settings.cycle_break_week ? 1 : 0" :options="[{ label: 'Yes', value: 1 }, { label: 'No', value: 0 }]" aria-label="Break week"
                data-setting="cycle_break_week" @update:model-value="(v) => d.is_admin && setOne('cycle_break_week', v)" />
            </SettingRow>
          </Card>
          <p class="text-sm text-ink-gray-6">{{ d.is_admin ? 'Changes save as you make them.' : 'Only the owner can change these.' }}</p>
        </template>

        <!-- Assistant: Sensitive items and Note rules -->
        <template v-else-if="section === 'sensitive'">
          <p class="text-sm text-ink-gray-6">A sensitive item is a document from the Vault, or a capture or note marked sensitive. Each space decides who may read them. Anyone who can edit an item may mark it; only the space's owner may unmark it.</p>
          <Card flush data-sensitive>
            <SettingRow v-for="sp in d.spaces" :key="sp.name" :label="`Ask may read sensitive items in ${sp.name}`" help="Off by default. Ask answers the people in the space." :data-sensitive-space="sp.name">
              <Switch :model-value="!!sp.ask_can_read_vault" :aria-label="`Ask may read sensitive items in ${sp.name}`" :data-ask-vault-switch="sp.name" :disabled="!d.is_admin"
                @update:model-value="(v) => setSpaceAsk(sp, 'ask_can_read_vault', v)" /></SettingRow>
          </Card>
          <p class="text-sm text-ink-gray-6" data-sensitive-agents-note>Whether agents may open sensitive items is set for each space under
            <RouterLink v-if="d.is_admin" class="text-ink-blue-8 hover:underline" :to="{ query: { ...route.query, tab: 'spaces' } }">People and agents, Spaces</RouterLink><template v-else>People and agents, Spaces, by the owner</template>.</p>
        </template>
        <template v-else-if="section === 'note-rules'">
          <p class="text-sm text-ink-gray-6">The assistant reads this page before it writes its notes. People edit it; agents cannot. It is also pinned at the top of the assistant's notes in the Library.</p>
          <NoteEditor v-if="rulesDoc" :key="rulesDoc.name" :note="rulesDoc" data-settings-rules />
          <Card v-else><Empty title="No rules page yet in this space." hint="It is made the first time the assistant reads the rules." /></Card>
        </template>

        <!-- People and agents: Spaces -->
        <template v-else-if="section === 'spaces'">
          <div class="flex flex-col gap-4" data-settings-spaces>
            <Card v-for="sp in d.spaces" :key="sp.name" flush :data-space-card="sp.name">
              <div class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 py-2.5">
                <div class="min-w-0 flex-1 basis-48"><div class="text-base-medium text-ink-gray-9">{{ sp.name }}</div>
                  <div class="text-sm text-ink-gray-6" :data-space-counts="sp.name">Owner {{ sp.owner_name || '—' }} · {{ plural(sp.people_count, 'person', 'people') }} · {{ plural(sp.agent_count, 'agent', 'agents') }}</div></div>
                <Button size="sm" label="Members" :data-space-members="sp.name" @click="showMembers(sp.name)" />
              </div>
              <SettingRow label="Ask in this space" help="People in this space can ask about its records.">
                <Switch :model-value="!!sp.ask_enabled" :aria-label="`Ask in ${sp.name}`" :data-ask-switch="sp.name" @update:model-value="(v) => setSpaceAsk(sp, 'ask_enabled', v)" /></SettingRow>
              <SettingRow label="Agents may open sensitive items" help="Off by default. With it off, agents cannot list, read or download this space's sensitive items.">
                <Switch :model-value="!!sp.agents_can_read_vault" :aria-label="`Agents may open sensitive items in ${sp.name}`" :data-vault-switch="sp.name"
                  @update:model-value="(v) => setVault(sp, v)" /></SettingRow>
            </Card>
          </div>
          <p class="text-sm text-ink-gray-6">Each record lives in one space. A person or an agent sees a space's records only as its member.</p>
        </template>

        <!-- Data -->
        <template v-else-if="section === 'import'">
          <ConnectionsSection :space="spaceSel" :writable="canEdit && !store.isAgent" import-only />
        </template>
        <template v-else-if="section === 'backups' && d.backups">
          <Card flush data-settings-backups>
            <SettingRow label="Scheduled backups" :help="d.backups.configured ? 'From this site\'s configuration.' : 'Not set up on this site. Ask whoever runs the server to switch on backups.'">
              <Badge :theme="d.backups.configured ? 'green' : 'amber'" :label="d.backups.configured ? (d.backups.settings.backup_frequency || 'On') : 'Not set up on this site'" data-backups-state />
            </SettingRow>
            <SettingRow v-for="(v, k) in d.backups.settings" :key="k" :label="k.replace(/_/g, ' ')" help="Site configuration"><span class="text-base text-ink-gray-8">{{ v }}</span></SettingRow>
            <SettingRow label="Copies to S3" help="Frappe's S3 backup settings."><Badge :label="d.backups.s3 ? 'On' : 'Off'" /></SettingRow>
          </Card>
          <section v-if="d.backups.latest.length"><SectionHead>Latest backup files on this server</SectionHead>
            <Card flush><Row v-for="f in d.backups.latest" :key="f.name"><span class="min-w-0 flex-1 break-all text-sm text-ink-gray-8">{{ f.name }}</span>
              <span class="text-sm tabular-nums text-ink-gray-6">{{ (f.size / 1024).toFixed(0) }} KB</span></Row></Card></section>
          <p class="text-sm text-ink-gray-6">Backups hold the database (every record, including Life OS) and, when files are included, the uploaded files.</p>
        </template>

        <!-- Your life: Areas (issue 12): the seven areas of life with their parts; only Life Admin changes them -->
        <template v-else-if="section === 'areas'">
          <AreasSection :space="spaceSel" :rows="d.areas" :is-admin="!!d.is_admin" @changed="changed" />
          <!-- the sidebar's "Focus on an area": which areas are pinned there, and each area's dot -->
          <section id="pins" data-area-pins>
            <SectionHead>In the sidebar</SectionHead>
            <Card flush>
              <SettingRow v-for="a in shownAreas" :key="a.name" :label="(a.parent_area ? '· ' : '') + a.title" :help="a.parent_area ? 'Part' : 'Pinned areas are one-click lenses, in this order.'">
                <div class="flex items-center gap-2">
                  <span class="size-2.5 rounded-full" :class="dotClass(a)" aria-hidden="true" />
                  <Select class="w-28" :model-value="a.colour || 'gray'" :options="COLOURS" :disabled="!d.is_admin" :aria-label="`Colour of ${a.title}`" :data-area-colour="a.name"
                    @update:model-value="(v) => saveArea(a, { colour: v })" />
                  <Switch :model-value="!!a.is_pinned" :disabled="!d.is_admin" :aria-label="`Pin ${a.title} to the sidebar`" :data-area-pin="a.name"
                    @update:model-value="(v) => saveArea(a, { is_pinned: v ? 1 : 0 })" />
                </div>
              </SettingRow>
            </Card>
          </section>
        </template>
        <!-- This space -->
        <template v-else-if="listOf(section)">
          <SettingsList :kind="listOf(section).kind" :rows="active(listOf(section))" :noun="listOf(section).noun" :hint="listOf(section).hint" :ordered="listOf(section).ordered"
            :writable="canEdit" :count-noun="listOf(section).countNoun" :link="listOf(section).link" @rename="rename" @reorder="reorder" @archive="askArchive" />
          <p class="text-sm text-ink-gray-6">{{ listOf(section).footer }}</p>
        </template>
        <Card v-else-if="section === 'places'" flush data-settings-places>
          <!-- issue 14: the pages that left the sidebar, each with the place it lives in now -->
          <div v-for="p in ELSEWHERE" :key="p.key" class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 border-b border-outline-gray-1 px-4 py-2.5 last:border-b-0">
            <RouterLink class="text-base-medium text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="p.to" :data-elsewhere="p.key">{{ p.label }}</RouterLink>
            <span class="text-sm text-ink-gray-6">{{ p.home }}</span>
          </div>
        </Card>
        <template v-else-if="section === 'archive'">
          <Card flush>
            <SettingRow label="Archive after" help="Done and dropped tasks, and inbox items that are done, move to the Archive this many days after they were closed. Notes, documents, chats, journal pages and goals are never archived automatically."
              :error="errors.archive_after_days">
              <TextInput class="w-28" type="number" min="1" :model-value="d.settings.archive_after_days" :disabled="!d.is_admin" data-setting="archive_after_days"
                @change="(e) => setOne('archive_after_days', Number(e.target.value))"><template #suffix><span class="text-sm text-ink-gray-6">days</span></template></TextInput>
            </SettingRow>
            <SettingRow label="Task is stale after" help="An open task untouched for this many days is listed under Decide in the weekly review. Nothing is archived or changed by this." :error="errors.stale_task_days">
              <TextInput class="w-28" type="number" min="1" :model-value="d.settings.stale_task_days" :disabled="!d.is_admin" data-setting="stale_task_days"
                @change="(e) => setOne('stale_task_days', Number(e.target.value))"><template #suffix><span class="text-sm text-ink-gray-6">days</span></template></TextInput>
            </SettingRow>
            <p v-if="!d.is_admin" class="pb-3 text-sm text-ink-gray-6">Only the owner can change these.</p>
          </Card>
          <p class="text-sm text-ink-gray-6"><RouterLink class="text-ink-blue-8 hover:underline" to="/library/archive" data-archive-link>Archived records are in Library, Archive</RouterLink>,
            and deleted ones in its <RouterLink class="text-ink-blue-8 hover:underline" :to="{ path: '/library/archive', query: { type: 'trash' } }" data-trash-link>Trash</RouterLink>.
            Below are the headings archived from Areas, Tags, Habits and Check-ins in {{ spaceSel }}.</p>
          <section v-for="l in LISTS" :key="l.kind" :data-archived-group="l.kind">
            <SectionHead :count="archived(l).length">{{ l.label }}</SectionHead>
            <Card flush>
              <div v-for="r in archived(l)" :key="r.name" class="flex min-h-11 flex-wrap items-center gap-2 border-b border-outline-gray-1 py-1.5 last:border-b-0" :data-archived-row="r.name">
                <div class="min-w-0 flex-1"><div class="break-words text-base text-ink-gray-9">{{ r.title }}<span v-if="r.parentTitle" class="text-ink-gray-6"> · under {{ r.parentTitle }}</span></div>
                  <div class="text-sm text-ink-gray-6">{{ r.archived_on ? 'Archived ' + short(r.archived_on, true) : 'Archived before the date was kept' }} · {{ r.count }} {{ r.count === 1 ? l.countNoun[0] : l.countNoun[1] }}</div></div>
                <Button v-if="canEdit" label="Restore" :data-restore="r.name" @click="askRestore(l, r)" />
              </div>
              <Empty v-if="!archived(l).length" :title="`No archived ${l.noun}.`" />
            </Card>
          </section>
        </template>
        <Card v-else-if="section === 'reset'" flush data-reset-rules>
          <SettingRow label="Stuck after" help="An open task, open-ended goal or inbox item untouched for this many days counts as stuck: on Today, in Reset and in the insights." :error="errors.stuck_after_days">
            <TextInput class="w-28" type="number" min="1" :model-value="d.settings.stuck_after_days" :disabled="!d.is_admin" data-setting="stuck_after_days"
              @change="(e) => setOne('stuck_after_days', Number(e.target.value))"><template #suffix><span class="text-sm text-ink-gray-6">days</span></template></TextInput>
          </SettingRow>
          <SettingRow label="Stuck limit" help="Above this many stuck tasks, Today's Open band turns amber and Reset is highlighted." :error="errors.stuck_limit">
            <TextInput class="w-28" type="number" min="0" :model-value="d.settings.stuck_limit" :disabled="!d.is_admin" data-setting="stuck_limit"
              @change="(e) => setOne('stuck_limit', Number(e.target.value))"><template #suffix><span class="text-sm text-ink-gray-6">tasks</span></template></TextInput>
          </SettingRow>
          <SettingRow label="Open task goal" help="Reset's goal bar: keep open tasks under this number." :error="errors.open_task_goal">
            <TextInput class="w-28" type="number" min="0" :model-value="d.settings.open_task_goal" :disabled="!d.is_admin" data-setting="open_task_goal"
              @change="(e) => setOne('open_task_goal', Number(e.target.value))"><template #suffix><span class="text-sm text-ink-gray-6">tasks</span></template></TextInput>
          </SettingRow>
          <SettingRow label="Someday review after" help="A parked item comes back for review this long after it was parked." :error="errors.someday_review_months">
            <TextInput class="w-28" type="number" min="1" :model-value="d.settings.someday_review_months" :disabled="!d.is_admin" data-setting="someday_review_months"
              @change="(e) => setOne('someday_review_months', Number(e.target.value))"><template #suffix><span class="text-sm text-ink-gray-6">months</span></template></TextInput>
          </SettingRow>
          <SettingRow label="Inbox items not dealt with" help="What happens to items left in the Inbox, and after how many days. Items an agent is working on, and failed items, are never touched."
            :error="errors.old_inbox_mode || errors.old_inbox_days" data-old-inbox-rule>
            <div class="flex flex-wrap items-center gap-2">
              <Select class="w-56" :model-value="d.settings.old_inbox_mode || 'Suggest'" :options="OLD_INBOX" :disabled="!d.is_admin" aria-label="Inbox items not dealt with"
                data-setting="old_inbox_mode" @update:model-value="setOldInboxMode" />
              <span class="text-sm text-ink-gray-6">after</span>
              <TextInput class="w-24" type="number" min="1" :model-value="d.settings.old_inbox_days || 7" :disabled="!d.is_admin" data-setting="old_inbox_days"
                @change="(e) => setOne('old_inbox_days', Number(e.target.value))"><template #suffix><span class="text-sm text-ink-gray-6">days</span></template></TextInput>
            </div>
          </SettingRow>
          <p v-if="!d.is_admin" class="pb-3 text-sm text-ink-gray-6">Only the owner can change these.</p>
        </Card>
        <ConnectionsSection v-else-if="section === 'connections'" :space="spaceSel" :writable="canEdit && !store.isAgent" />

        <!-- Admin -->
        <template v-else-if="section === 'members'">
          <div class="flex gap-4 max-md:flex-col">
            <Select v-if="phone" :model-value="memberSpace" :options="d.spaces.map((s) => s.name)" aria-label="Space" @update:model-value="(v) => (memberSpace = v)" />
            <div v-else class="flex w-40 flex-none flex-col gap-0.5" data-member-spaces>
              <Button v-for="s in d.spaces" :key="s.name" class="!justify-start" :variant="s.name === memberSpace ? 'subtle' : 'ghost'" :label="s.name" :data-space="s.name" @click="memberSpace = s.name" />
            </div>
            <div v-if="mSpace" class="flex min-w-0 flex-1 flex-col gap-3">
              <TabButtons v-model="memberKind" class="self-start" :options="memberTabs" aria-label="Show" data-member-filter />
              <Card flush data-members>
                <MemberRow v-for="m in shownMembers" :key="m.user" :member="m" @access="(v) => setMember(mSpace.name, m.user, v)" @remove="askRemove(mSpace, m)" />
                <Empty v-if="!shownMembers.length" :title="memberKind === 'agents' ? `No agents in ${mSpace.name}.` : memberKind === 'people' ? `No people in ${mSpace.name}.` : 'No members.'"
                  hint="Add someone with Add member." />
              </Card>
            </div>
          </div>
          <p class="text-sm text-ink-gray-6">Everyone in a space, people and agents, sees its records. Can view lets them read; Can edit lets them add and change records.
            An agent's keys and its other spaces are under <RouterLink class="text-ink-blue-8 hover:underline" :to="{ query: { ...route.query, tab: 'agents' } }">Agents</RouterLink>.</p>
        </template>
        <template v-else-if="section === 'ai' && d.ai">
          <Card flush data-ai-settings>
            <SettingRow label="Anthropic API key" :help="d.ai.key_set ? 'A key is set. It is stored encrypted and never shown again.' : 'No key yet: Ask says it is not set up, and only rule insights run. Or set it with bench set-config anthropic_api_key.'">
              <div class="flex items-center gap-2">
                <TextInput v-model="aiKey" class="w-56" type="password" :placeholder="d.ai.key_set ? 'Replace the key' : 'sk-ant-…'" aria-label="Anthropic API key" autocomplete="off" data-ai-key />
                <Button label="Save" :disabled="!aiKey" data-ai-key-save @click="saveKey" />
                <Button v-if="d.ai.key_set" variant="ghost" theme="red" label="Remove" @click="saveKey(true)" />
              </div>
            </SettingRow>
            <SettingRow label="Ask model" help="Writes Ask's answers and the AI insights.">
              <TextInput class="w-56" :model-value="d.settings.ask_model" data-setting="ask_model" @change="(e) => setOne('ask_model', e.target.value.trim())" /></SettingRow>
            <SettingRow label="Short-task model" help="For short wording jobs.">
              <TextInput class="w-56" :model-value="d.settings.short_model" data-setting="short_model" @change="(e) => setOne('short_model', e.target.value.trim())" /></SettingRow>
            <SettingRow label="Monthly cap" help="Ask and the AI insights stop for the month when the spend reaches this." :error="errors.monthly_cap_usd">
              <TextInput class="w-28" type="number" min="0" :model-value="d.settings.monthly_cap_usd" data-setting="monthly_cap_usd"
                @change="(e) => setOne('monthly_cap_usd', Number(e.target.value))"><template #prefix><span class="text-sm text-ink-gray-6">$</span></template></TextInput></SettingRow>
          </Card>
          <section>
            <SectionHead>This month</SectionHead>
            <Card flush data-ai-spend>
              <Row><span class="flex-1 text-base text-ink-gray-9">{{ d.ai.spend.text }}</span></Row>
              <Row v-for="p in d.ai.by_purpose" :key="p.purpose"><span class="flex-1 text-base text-ink-gray-8">{{ p.purpose }}</span>
                <span class="text-sm tabular-nums text-ink-gray-6">{{ (p.input_tokens + p.output_tokens).toLocaleString() }} tokens · ${{ p.cost.toFixed(2) }}</span></Row>
              <Row v-for="u in d.ai.by_user" :key="u.user"><span class="flex-1 text-base text-ink-gray-8">{{ u.full_name }}</span><span class="text-sm tabular-nums text-ink-gray-6">${{ u.cost.toFixed(2) }}</span></Row>
            </Card>
          </section>
          <section>
            <SectionHead>Prices per model</SectionHead>
            <Card flush>
              <Row v-for="pr in d.ai.prices" :key="pr.model" class="flex-wrap !items-center"><span class="min-w-40 flex-1 text-base text-ink-gray-8">{{ pr.model }}</span>
                <TextInput class="w-28" type="number" min="0" step="0.01" :model-value="pr.input_per_mtok" :aria-label="`${pr.model} input price`" @change="(e) => setPrice(pr, 'input_per_mtok', e.target.value)"><template #suffix><span class="text-sm text-ink-gray-6">in</span></template></TextInput>
                <TextInput class="w-28" type="number" min="0" step="0.01" :model-value="pr.output_per_mtok" :aria-label="`${pr.model} output price`" @change="(e) => setPrice(pr, 'output_per_mtok', e.target.value)"><template #suffix><span class="text-sm text-ink-gray-6">out</span></template></TextInput></Row>
            </Card>
            <p class="mt-1 text-sm text-ink-gray-6">US dollars per million tokens.</p>
          </section>
          <p class="text-sm text-ink-gray-6" data-ai-spaces-note>Ask is switched on or off for each space under
            <RouterLink class="text-ink-blue-8 hover:underline" :to="{ query: { ...route.query, tab: 'spaces' } }">People and agents, Spaces</RouterLink>.</p>
        </template>
        <template v-else-if="section === 'agents'">
          <Card v-for="a in d.agents" :key="a.user" flush :data-agent="a.user">
            <div class="flex flex-wrap items-center gap-2.5 border-b border-outline-gray-1 py-2.5">
              <Avatar size="md" :label="a.full_name" :image="a.image" />
              <div class="min-w-0 flex-1 basis-40"><div class="break-words text-base-medium text-ink-gray-9">{{ a.full_name }}</div>
                <div class="break-all text-sm text-ink-gray-6">{{ a.user }}</div>
                <div class="text-sm text-ink-gray-6" data-agent-last>{{ a.last_filed ? 'Last filed something ' + dateTime(a.last_filed) : 'Has not filed anything yet' }}</div></div>
              <Badge theme="blue" label="Agent" />
              <Button size="sm" icon-right="lucide-external-link" label="Keys in Frappe" :href="`/app/user/${encodeURIComponent(a.user)}`" :data-agent-user-link="a.user" />
            </div>
            <div v-for="r in a.spaces" :key="r.space" class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 py-2 last:border-b-0" :data-agent-space="a.user + '|' + r.space">
              <span class="min-w-24 flex-1 text-base text-ink-gray-8">{{ r.space }}</span>
              <span class="text-sm text-ink-gray-6" :data-agent-sensitive="a.user + '|' + r.space">{{ r.agents_can_read_vault ? 'Opens sensitive items' : 'No sensitive items' }}</span>
              <Select class="w-36" :model-value="r.access || ''" :options="AGENT_ACCESS" :aria-label="`${a.full_name} in ${r.space}`" :data-agent-access="a.user + '|' + r.space"
                @update:model-value="(v) => setAgent(r.space, a.user, v, r.access)" />
            </div>
          </Card>
          <Card v-if="!d.agents.length"><Empty title="No agents yet." data-agents-empty
            hint="An agent is a Frappe user that only an assistant signs in as. Create the user in Frappe, then add it to a space with Add member under Members: Life OS offers it agent access there." /></Card>
          <p class="text-sm text-ink-gray-6">Whether agents may open sensitive items is set for each space under
            <RouterLink class="text-ink-blue-8 hover:underline" :to="{ query: { ...route.query, tab: 'spaces' } }">Spaces</RouterLink>.
            Keys for agents are made in Frappe, never on this screen.</p>
        </template>
      </div>
    </section>
  </div>

  <Dialog v-model:open="newOpen" :title="'New ' + (listOf(section)?.one || '')" size="sm"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Add', variant: 'solid', onClick: create }]">
    <div class="flex flex-col gap-3">
      <TextInput v-model="draft.title" :placeholder="listOf(section)?.placeholder" aria-label="Name" data-new-name @keydown.enter="create" />
    </div>
  </Dialog>
  <Dialog v-model:open="archiveOpen" :title="`Archive ${archiving?.row.title || ''}?`" size="md"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Archive', variant: 'solid', onClick: archive }]">
    <div class="flex flex-col gap-2 text-base text-ink-gray-8" data-archive-dialog>
      <p>It leaves the {{ archiving?.l.kind === 'tag' ? 'tag pickers' : archiving?.l.kind === 'habit' ? 'habit pickers' : 'check-in form' }}. Past records that use it keep it.</p>
      <p class="text-sm text-ink-gray-6">Nothing is deleted. Restore it from Archived in Settings.</p>
    </div>
  </Dialog>
  <AddMemberDialog v-if="memberSpace" v-model:open="addOpen" :space="memberSpace" @added="load" />
  <Dialog v-model:open="spaceOpen" title="New space" size="sm"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Create space', variant: 'solid', onClick: createSpace }]">
    <div class="flex flex-col gap-3">
      <TextInput v-model="newSpace.name" label="Name" placeholder="For example Anya" />
      <LifeLink v-model="newSpace.owner" doctype="User" label="Owner" placeholder="You, unless you choose someone" />
      <p class="text-sm text-ink-gray-6">A new space starts with four areas: Work, Personal &amp; Health, Money &amp; Legal and Family. Rename or archive them later.</p>
    </div>
  </Dialog>
</template>
<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
// A routed page, not frappe-ui's SettingsDialog: that family's panels only work inside the dialog. The menu is frappe-ui
// Tabs in its vertical form, with the open section in the URL (tab=).
import { Avatar, Badge, Button, Dialog, KeyboardShortcut, Select, Skeleton, Switch, TabButtons, TabList, Tabs, TabTrigger, TextInput, TimePicker, dialog, toast, useColorScheme } from 'frappe-ui'
import NoteEditor from '@/components/NoteEditor.vue'
import { ELSEWHERE, GO } from '@/lib/nav'
import { dotClass } from '@/lib/lens'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import CalendarSection from '@/components/settings/CalendarSection.vue'
import AreasSection from '@/components/settings/AreasSection.vue'
import SettingRow from '@/components/settings/SettingRow.vue'
import SettingsList from '@/components/settings/SettingsList.vue'
import ConnectionsSection from '@/components/settings/ConnectionsSection.vue'
import MemberRow from '@/components/settings/MemberRow.vue'
import AddMemberDialog from '@/components/settings/AddMemberDialog.vue'
import LifeLink from '@/framework/LifeLink.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { boot, store } from '@/lib/store'
import { loadLookups } from '@/lib/lookups'
import { dateTime, short } from '@/lib/dates'

const COLOURS = ['blue', 'green', 'amber', 'red', 'violet', 'teal', 'orange', 'pink', 'cyan', 'gray'].map((c) => ({ label: c[0].toUpperCase() + c.slice(1), value: c }))
const hm = (t) => (t ? String(t).padStart(8, '0').slice(0, 5) : '06:00')
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
// set 7: Inbox items not dealt with. Each choice brings its own default number of days, unless the days were changed by hand
const OLD_INBOX = [{ label: 'Suggest decisions', value: 'Suggest' }, { label: 'Park them as ideas', value: 'Park' }, { label: 'Discard them to the trash', value: 'Discard' }]
const OLD_INBOX_DAYS = { Suggest: 7, Park: 14, Discard: 14 }
async function setOldInboxMode(v) {
  const was = d.value.settings.old_inbox_mode || 'Suggest'
  const days = Number(d.value.settings.old_inbox_days || 7)
  await setOne('old_inbox_mode', v)
  if (days === OLD_INBOX_DAYS[was] && days !== OLD_INBOX_DAYS[v]) await setOne('old_inbox_days', OLD_INBOX_DAYS[v])
}
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const workDays = computed(() => String(d.value?.settings.work_days || 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday').split(',').filter(Boolean))
function toggleDay(day) {
  const set = workDays.value.includes(day) ? workDays.value.filter((x) => x !== day) : [...workDays.value, day]
  if (set.length) setOne('work_days', WEEKDAYS.filter((x) => set.includes(x)).join(','))
}
const SCHEMES = [{ label: 'Light', value: 'light' }, { label: 'Dark', value: 'dark' }, { label: 'System', value: 'system' }]
const AGENT_ACCESS = [{ label: 'No access', value: '' }, { label: 'Can view', value: 'Read' }, { label: 'Can edit', value: 'Write' }]
const LISTS = [
  { kind: 'area', section: 'areas', label: 'Areas', one: 'area', noun: 'areas', key: 'areas', field: 'area_name', ordered: true, placeholder: 'For example Health',
    hint: 'Areas are your own filing headings.', countNoun: ['record', 'records'], link: (r) => ({ path: '/library/timeline', query: { area: r.name } }),
    footer: 'Drag the handle to reorder, or to the middle of another area to put it under that one. Alt and the arrow keys move a focused row.' },
  { kind: 'tag', section: 'tags', label: 'Tags', one: 'tag', noun: 'tags', key: 'tags', field: 'tag_name', placeholder: 'For example tax',
    hint: 'Tags are themes that cut across areas.', countNoun: ['tagged record', 'tagged records'], footer: 'Tags are listed by name.' },
  { kind: 'habit', section: 'habits', label: 'Habits', one: 'habit', noun: 'habits', key: 'habits', field: 'title', placeholder: 'For example Walk',
    hint: 'Habits you may track in a month.', countNoun: ['month', 'months'], footer: 'This is the library of habits ever tracked. Which ones count in a month is set under Journal, Habits, Manage habits.' },
  { kind: 'dimension', section: 'dimensions', label: 'Check-in dimensions', one: 'dimension', noun: 'dimensions', key: 'dimensions', field: 'dimension_name', ordered: true,
    placeholder: 'For example Health', hint: 'The life dimensions scored in a check-in.', countNoun: ['check-in', 'check-ins'], footer: 'Dimensions show in the check-in form in this order.' },
]
const route = useRoute()
const router = useRouter()
const phone = useMediaQuery('(max-width: 767px)')
const { colorScheme, setColorScheme } = useColorScheme()
const d = ref(null)
const errors = reactive({})
const newOpen = ref(false)
const draft = reactive({ title: '' })
const archiveOpen = ref(false)
const archiving = ref(null)
const addOpen = ref(false)
const spaceOpen = ref(false)
const newSpace = reactive({ name: '', owner: null })
const memberSpace = ref('')

// The menu (UX fixes, set 6): Me; Your life (in the space picked here); Assistant; People and agents; Data.
const groups = computed(() => [
  { key: 'me', label: 'Me', items: [{ value: 'profile', label: 'Profile' }, { value: 'appearance', label: 'Appearance' }, { value: 'notifications', label: 'Notifications' },
    { value: 'shortcuts', label: 'Shortcuts' }, { value: 'calendar', label: 'Calendar' }] },
  { key: 'space', label: 'Your life', items: [{ value: 'areas', label: 'Areas' }, { value: 'rhythms', label: 'Rhythms' }, { value: 'habits', label: 'Habits' },
    { value: 'dimensions', label: 'Check-ins' }, { value: 'reset', label: 'Reset rules' }, { value: 'tags', label: 'Tags' }] },
  { key: 'assistant', label: 'Assistant', items: [{ value: 'connections', label: 'Connections' },
    ...(d.value?.is_admin ? [{ value: 'ai', label: 'Ask and AI' }] : []), { value: 'sensitive', label: 'Sensitive items' }, { value: 'note-rules', label: 'Note rules' }] },
  // issue 1: who is in each space and what they can do, people and agents together
  ...(d.value?.is_admin ? [{ key: 'people', label: 'People and agents', items: [{ value: 'spaces', label: 'Spaces' }, { value: 'members', label: 'Members' },
    { value: 'agents', label: 'Agents' }] }] : []),
  { key: 'data', label: 'Data', items: [{ value: 'archive', label: 'Archive and trash' }, { value: 'import', label: 'Import and export' },
    { value: 'places', label: 'Where things are' },
    ...(d.value?.is_admin ? [{ value: 'backups', label: 'Backups' }] : [])] },
])
// sections from before set 6 and issue 1, by their new names (tab=agents keeps its name: it is now People and agents, Agents)
const MOVED = { default: 'profile', review: 'rhythms', archived: 'archive', assistants: 'agents', people: 'members' }
const sections = computed(() => groups.value.flatMap((g) => g.items))
// the open section is tab= in the URL. On a wide screen the first section is the default; on a phone the menu is.
const ADMIN_ONLY = ['members', 'spaces', 'agents', 'ai', 'backups']
const section = computed(() => {
  const asked = route.query.tab ? String(route.query.tab) : ''
  const v = MOVED[asked] || asked
  // an Admin section asked for before the settings have loaded is kept; once loaded, only a Life Admin has it
  if (sections.value.some((s) => s.value === v) || (!d.value && ADMIN_ONLY.includes(v))) return v
  return phone.value ? '' : 'profile'
})
function open(v) {
  if (v === section.value) return
  router.push({ query: { ...route.query, tab: v && (phone.value || v !== 'profile') ? v : undefined } })
}
// "This space": its own space picker, which does not change the space of the sidebar (space= in the URL)
const spaceSel = computed(() => (route.query.space ? String(route.query.space) : store.space))
const pickSpace = (v) => router.replace({ query: { ...route.query, space: v === store.space ? undefined : v } })
const spaceGroup = ['areas', 'tags', 'habits', 'dimensions', 'connections', 'note-rules', 'import']
const heading = computed(() => {
  const label = section.value === 'areas' ? 'Areas of life' : sections.value.find((s) => s.value === section.value)?.label || ''
  return spaceGroup.includes(section.value) ? `${label} in ${spaceSel.value}` : label
})
const canEdit = computed(() => d.value?.spaces.find((s) => s.name === spaceSel.value)?.access === 'Write')
const listOf = (sec) => LISTS.find((l) => l.section === sec)
const rowsOf = (l) => (d.value?.[l.key] || []).map((x) => ({ ...x, title: x[l.field] }))
const active = (l) => rowsOf(l).filter((x) => !x.is_archived)
function archived(l) {
  const all = rowsOf(l)
  return all.filter((x) => x.is_archived).map((x) => ({ ...x, parentTitle: x.parent_area ? all.find((p) => p.name === x.parent_area)?.title : null }))
}
// the areas the sidebar may pin: those that are on, each area of life followed by its parts
const shownAreas = computed(() => {
  const all = active(LISTS[0])
  const on = all.filter((a) => a.is_life_area && a.is_on)
  return on.flatMap((a) => [a, ...all.filter((p) => p.parent_area === a.name && p.is_on)])
})
const mSpace = computed(() => d.value?.spaces.find((s) => s.name === memberSpace.value))
// Members: All, People, Agents, with counts
const memberKind = ref('all')
const memberTabs = computed(() => {
  const all = mSpace.value?.members || []
  const agents = all.filter((m) => m.is_agent).length
  return [{ label: `All ${all.length}`, value: 'all' }, { label: `People ${all.length - agents}`, value: 'people' }, { label: `Agents ${agents}`, value: 'agents' }]
})
const shownMembers = computed(() => (mSpace.value?.members || []).filter((m) => memberKind.value === 'all' || m.is_agent === (memberKind.value === 'agents')))
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`

// Note rules: the rules page of the assistant's notes in this space
const rulesDoc = ref(null)
watch(() => [section.value, d.value?.rules_note], async ([sec, name]) => {
  if (sec === 'note-rules' && name && rulesDoc.value?.name !== name) rulesDoc.value = await tryCall(() => api('library.get', { note: name }))
}, { immediate: true })
// an area's dot and its pin in the sidebar
async function saveArea(a, values) {
  const before = { colour: a.colour, is_pinned: a.is_pinned }
  Object.assign(a, values)
  if (await tryCall(() => api('settings.save_item', { kind: 'area', name: a.name, ...values }), 'Saved')) changed()
  else Object.assign(a, before)
}
async function load() {
  const res = await tryCall(() => api('settings.get', { space: spaceSel.value }))
  if (!res) return
  if (res.settings.weekly_review_time) res.settings.weekly_review_time = String(res.settings.weekly_review_time).padStart(8, '0').slice(0, 5)
  d.value = res
  if (!res.spaces.some((s) => s.name === memberSpace.value)) memberSpace.value = res.spaces.find((s) => s.name === store.space)?.name || res.spaces[0]?.name || ''
}
// the sidebar, pickers and filters read the lists again at once
async function changed() {
  await load()
  await loadLookups(true)
  window.dispatchEvent(new CustomEvent('lifeos-areas-changed'))
}

// ---- plain settings: each saves on its own; an error shows under the field and the old value comes back ----
const aiKey = ref('')
async function saveKey(clear = false) {
  const res = await tryCall(() => api('settings.set_ai_key', { key: clear === true ? '' : aiKey.value }), clear === true ? 'Key removed' : 'Key saved')
  aiKey.value = ''
  if (res) await load()
}
async function setPrice(pr, field, value) {
  pr[field] = Number(value)
  if (await tryCall(() => api('settings.set_ai_price', { model: pr.model, input_per_mtok: pr.input_per_mtok, output_per_mtok: pr.output_per_mtok }), 'Saved')) await load()
}
async function setSpaceAsk(sp, field, value) {
  const before = sp[field]
  sp[field] = value ? 1 : 0
  if (!(await tryCall(() => api('settings.set_space_ask', { space: sp.name, [field]: value ? 1 : 0 }), 'Saved'))) sp[field] = before
}
async function setOne(field, value) {
  const before = d.value.settings[field]
  if (value === before) return
  errors[field] = ''
  d.value.settings[field] = value
  let v = value
  if (['weekly_review_time', 'start_of_day', 'work_start', 'work_end'].includes(field) && v && v.length === 5) v += ':00'
  try {
    await api('settings.save', { values: { [field]: v } })
    toast.success('Saved')
    if (field === 'default_space') boot()
  } catch (e) {
    errors[field] = errorText(e)
    d.value.settings[field] = before
  }
}

// ---- the four lists ----
async function rename(r, title) {
  const l = listOf(section.value)
  if (await tryCall(() => api('settings.save_item', { kind: l.kind, name: r.name, title }), 'Renamed')) changed()
}
async function reorder(names, parent) {
  const l = listOf(section.value)
  if (await tryCall(() => api('settings.reorder', { kind: l.kind, names, parent_area: l.kind === 'area' ? parent || '' : undefined }), 'Saved')) changed()
}
async function create() {
  const l = listOf(section.value)
  const title = draft.title.trim()
  if (!title) return
  const n = active(l).length
  const extra = l.ordered ? { sort_order: n + 1 } : {}
  if (await tryCall(() => api('settings.save_item', { kind: l.kind, space: spaceSel.value, title, ...extra }), 'Added')) {
    newOpen.value = false
    draft.title = ''
    changed()
  }
}
function askArchive(r) {
  archiving.value = { l: listOf(section.value), row: r }
  archiveOpen.value = true
}
async function archive() {
  const { l, row } = archiving.value
  archiveOpen.value = false
  if (await tryCall(() => api('settings.save_item', { kind: l.kind, name: row.name, is_archived: 1 }), 'Archived')) changed()
}
function askRestore(l, r) {
  const kids = l.kind === 'area' ? archived(l).filter((x) => x.parent_area === r.name && (!r.archived_on || x.archived_on === r.archived_on)) : []
  if (!kids.length) return restore(l, r, 0)
  dialog.confirm({
    title: `Restore ${r.title}`, message: `${kids.length} sub-area${kids.length === 1 ? ' was' : 's were'} archived with it: ${kids.map((k) => k.title).join(', ')}. Restore ${kids.length === 1 ? 'it' : 'them'} too?`,
    actions: [{ label: 'Only this area', onClick: ({ close }) => { close(); return restore(l, r, 0) } },
      { label: 'Restore with sub-areas', variant: 'solid', onClick: ({ close }) => { close(); return restore(l, r, 1) } }],
  })
}
async function restore(l, r, withChildren) {
  if (await tryCall(() => api('settings.save_item', { kind: l.kind, name: r.name, is_archived: 0, with_children: withChildren }), 'Restored')) changed()
}

// ---- members, spaces and agents ----
async function setMember(space, user, access, remove = 0) {
  if (await tryCall(() => api('settings.set_member', { space, user, access, remove }), remove ? 'Removed' : 'Saved')) {
    await load()
    return true
  }
}
function askRemove(space, m) {
  dialog.danger({ title: `Remove ${m.full_name}?`, message: `${m.full_name} will no longer see anything in ${space.name}. Their records stay.`, confirmLabel: 'Remove',
    onConfirm: async () => { await setMember(space.name, m.user, m.access, 1) } })
}
function showMembers(space) {
  memberSpace.value = space
  memberKind.value = 'all'
  open('members')
}
async function createSpace() {
  if (!newSpace.name.trim()) return toast.error('A name is needed.')
  if (await tryCall(() => api('settings.create_space', { space_name: newSpace.name, owner_user: newSpace.owner || undefined }), 'Space created')) {
    spaceOpen.value = false
    memberSpace.value = newSpace.name.trim()
    newSpace.name = ''
    newSpace.owner = null
    await boot()
    load()
  }
}
// the Agents view changes access with the same method as Members: set_member
async function setAgent(space, user, access, before) {
  if ((access || '') === (before || '')) return
  await setMember(space, user, access || before, access ? 0 : 1)
}
async function setVault(s, on) {
  if (await tryCall(() => api('settings.set_agent_vault', { space: s.name, allowed: on ? 1 : 0 }), 'Saved')) load()
}

watch(spaceSel, load, { immediate: true })
</script>
