<template>
  <PageHead title="Settings" :sub="store.fullName || store.user" />
  <div class="flex min-h-0 flex-1 max-md:block" data-settings>
    <!-- the menu: Me, Your life, Brain, People and agents, and Advanced at the foot. Items appear by level on the ladder; a Life Admin sees all.
         On a phone it is the first screen and a section opens full width with Back. -->
    <nav v-if="!phone || !section" class="flex w-60 flex-none flex-col overflow-y-auto border-r border-outline-gray-1 px-3 pb-6 pt-4 max-md:w-auto max-md:border-r-0 max-md:p-4" aria-label="Settings sections" data-settings-menu>
      <!-- wide screens: frappe-ui Tabs in its vertical form; a phone: the same groups as a list of rows, the first screen -->
      <Tabs v-if="!phone && ready" vertical :model-value="section" @update:model-value="onTab">
        <TabList variant="ghost" class="w-full">
          <template v-for="g in groups" :key="g.key">
            <div v-if="g.key === 'advanced'" class="mb-1 mt-4 border-t border-outline-gray-1" />
            <div v-if="g.label" class="px-2 pb-1 pt-4 text-sm-medium text-ink-gray-6 first:pt-0" :data-settings-group="g.key">{{ g.key === 'space' && manySpaces ? `${g.label} · ${spaceSel}` : g.label }}</div>
            <div v-if="g.key === 'space' && manySpaces" class="mb-1.5 px-1" @keydown.stop>
              <Select :model-value="spaceSel" :options="d.spaces.map((s) => ({ label: s.name, value: s.name }))" aria-label="Space for these settings" data-settings-space
                @update:model-value="pickSpace" />
            </div>
            <TabTrigger v-for="it in g.items" :key="it.value" class="w-full justify-start" :value="it.value" :label="it.label" :data-section="it.value" @click="open(it.value)" />
          </template>
        </TabList>
      </Tabs>
      <template v-else-if="ready">
        <section v-for="g in groups" :key="g.key" class="mb-4 flex flex-col gap-0.5">
          <div v-if="g.label" class="mb-1 text-sm-medium text-ink-gray-6" :data-settings-group="g.key">{{ g.label }}</div>
          <div v-if="g.key === 'space' && manySpaces" class="mb-1.5">
            <Select :model-value="spaceSel" :options="d.spaces.map((s) => ({ label: s.name, value: s.name }))" aria-label="Space for these settings" data-settings-space
              @update:model-value="pickSpace" />
          </div>
          <Button v-for="it in g.items" :key="it.value" class="!justify-start" size="lg" variant="ghost" icon-right="lucide-chevron-right" :label="it.label" :data-section="it.value"
            @click="open(it.value)" />
        </section>
      </template>
      <p v-if="ready && later" class="mt-auto px-2 pt-6 text-sm text-ink-gray-6" data-settings-later>More settings appear as you go up the ladder: {{ later }}</p>
    </nav>

    <section v-if="section && (!phone || section)" class="min-w-0 flex-1 overflow-y-auto px-7 pb-16 pt-6 max-md:p-4" data-settings-section :data-current="section">
      <div class="flex max-w-[720px] flex-col gap-4">
        <Button v-if="phone" class="-ml-2 self-start" variant="ghost" icon-left="lucide-arrow-left" label="Settings" data-settings-back @click="open('')" />
        <div class="flex items-center gap-3">
          <h2 class="min-w-0 flex-1 text-lg-semibold text-ink-gray-9" data-section-title>{{ heading }}</h2>
          <Button v-if="section === 'habits' && canEdit" variant="solid" icon-left="lucide-plus" label="New habit" data-new @click="openNew(habitsList)" />
          <Button v-if="section === 'members' && memberKind !== 'spaces' && memberSpace" variant="solid" icon-left="lucide-plus" label="Add member" data-add-member @click="addOpen = true" />
          <Button v-if="section === 'members' && memberKind === 'spaces' && manySpaces" label="New space" data-new-space @click="spaceOpen = true" />
        </div>
        <div v-if="!d" class="flex flex-col gap-3"><Skeleton v-for="i in 4" :key="i" class="h-10 w-full rounded-4" /></div>

        <template v-else>
        <!-- Profile: the person, Look and Reminders -->
        <template v-if="show('profile')">
          <SectionHead>Profile</SectionHead>
        <Card flush data-settings-profile>
          <SettingRow label="Name" help="How Life OS greets you and labels what you write. It comes from your Frappe user.">
            <span class="text-base text-ink-gray-9">{{ store.fullName || store.user }}</span></SettingRow>
          <SettingRow label="Email" help="You sign in with this address."><span class="break-all text-base text-ink-gray-8">{{ store.user }}</span></SettingRow>
          <SettingRow v-if="manySpaces" label="Default space" help="The space the app opens in, and where new records go when no space is chosen." :error="errors.default_space">
            <Select class="w-44" :model-value="d.settings.default_space" :options="d.spaces.map((s) => s.name)" :disabled="!d.is_admin" data-setting="default_space"
              @update:model-value="(v) => setOne('default_space', v)" />
          </SettingRow>
          <p v-if="!d.is_admin && manySpaces" class="pb-3 text-sm text-ink-gray-6">Only the owner can change this.</p>
        </Card>
          <SectionHead>Look</SectionHead>
        <Card flush data-settings-look>
          <SettingRow label="Theme" help="Light, dark, or follow the system setting of this device.">
            <TabButtons :model-value="colorScheme" :options="SCHEMES" aria-label="Theme" data-theme-switch @update:model-value="setColorScheme" />
          </SettingRow>
        </Card>
          <!-- issue 50: install Life OS on the phone's home screen, share to it, capture offline -->
          <SectionHead>Install on this phone</SectionHead>
        <Card flush data-settings-install>
          <SettingRow label="Android (Chrome)" help="Open the menu (three dots), then Install app or Add to Home screen. Life OS then opens full screen, and appears in the Share list of other apps: photos, PDFs, links and text."
            data-install-android><Badge v-if="platform === 'android'" theme="blue" label="This phone" /></SettingRow>
          <SettingRow label="iPhone and iPad (Safari)" help="Tap Share, then Add to Home Screen. Text and links can be shared to Life OS from other apps. iOS does not yet let a web app receive shared photos or files, so add those with + Capture."
            data-install-ios><Badge v-if="platform === 'ios'" theme="blue" label="This phone" /></SettingRow>
          <p class="pb-3 text-sm text-ink-gray-6">With no connection, + Capture keeps what you capture on the phone and sends it when you are back online. Nothing else works offline.</p>
        </Card>
          <SectionHead>Reminders</SectionHead>
        <Card flush data-settings-notifications>
          <SettingRow label="Reminders on Today" help="The weekly review, the month plan and the 12 Week cycle show as one line at the top of Today when they are due. Each has Skip.">
            <Badge theme="green" label="On" /></SettingRow>
          <SettingRow label="Email and phone" help="Life OS sends no email or push messages. Your agents may write to you in their own chats.">
            <Badge label="None" /></SettingRow>
          <p class="pb-3 text-sm text-ink-gray-6">When each rhythm happens is set under Your life, Rhythms.</p>
        </Card>
          <p class="text-sm text-ink-gray-6" data-settings-shortcuts>Keyboard shortcuts: press ? anywhere.</p>
          <SectionHead>Where things are</SectionHead>
        <Card flush data-settings-places>
          <!-- issue 26: How it works is reached from here and from the sidebar's setup card -->
          <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 border-b border-outline-gray-1 px-4 py-2.5">
            <RouterLink class="text-base-medium text-ink-blue-8 hover:underline focus-visible:focus-ring" to="/how-it-works" data-settings-how>How it works</RouterLink>
            <span class="text-sm text-ink-gray-6">Sources, the Brain, your plan and the ladder of six levels</span>
          </div>
          <!-- issue 14: the pages that left the sidebar, each with the place it lives in now -->
          <div v-for="p in ELSEWHERE" :key="p.key" class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 border-b border-outline-gray-1 px-4 py-2.5 last:border-b-0">
            <RouterLink class="text-base-medium text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="p.to" :data-elsewhere="p.key">{{ p.label }}</RouterLink>
            <span class="text-sm text-ink-gray-6">{{ p.home }}</span>
          </div>
        </Card>
        </template>
        <CalendarSection v-if="show('calendar')" />
        <!-- Rhythms: the weekly review (with the old-items rules), working hours and the 12 Week Year -->
        <template v-if="show('rhythms')">
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
          <SectionHead>Old items and stuck work</SectionHead>
        <Card flush data-reset-rules>
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
          <SectionHead>12 Weeks</SectionHead>
          <Card flush>
            <SettingRow label="Current cycle" :help="d.cycle ? `Week ${d.cycle.week} of 12. The next cycle can be planned from week 11.` : 'No cycle is running. Start one on Goals, Cycles.'">
              <span class="text-sm text-ink-gray-7" data-current-cycle>{{ d.cycle ? `${short(d.cycle.start_date)} to ${short(d.cycle.end_date, true)}` : '—' }}</span>
            </SettingRow>
            <SettingRow label="Score target" help="The weekly share of planned actions you aim to complete, in per cent." :error="errors.score_target">
              <TextInput class="w-28" type="number" min="1" max="100" :model-value="d.settings.score_target" :disabled="!d.is_admin" data-setting="score_target"
                @change="(e) => setOne('score_target', Number(e.target.value))"><template #suffix><span class="text-sm text-ink-gray-6">%</span></template></TextInput>
            </SettingRow>
            <SettingRow label="Plan in 12 Week Years or quarters" help="A 12-week goal follows your 12 Week Year cycle, or the calendar quarter." :error="errors.planning_period">
              <TabButtons :model-value="d.settings.planning_period || '12 Week Years'" :options="[{ label: '12 Week Years', value: '12 Week Years' }, { label: 'Quarters', value: 'Quarters' }]"
                aria-label="Plan in 12 Week Years or quarters" data-setting="planning_period" @update:model-value="(v) => d.is_admin && setOne('planning_period', v)" />
            </SettingRow>
            <SettingRow label="Break week" help="A week between cycles for review and planning." :error="errors.cycle_break_week">
              <TabButtons :model-value="d.settings.cycle_break_week ? 1 : 0" :options="[{ label: 'Yes', value: 1 }, { label: 'No', value: 0 }]" aria-label="Break week"
                data-setting="cycle_break_week" @update:model-value="(v) => d.is_admin && setOne('cycle_break_week', v)" />
            </SettingRow>
          </Card>
          <SectionHead>Goals</SectionHead>
          <Card flush data-settings-goals>
            <SettingRow label="Require “Done when” on new goals" help="A new goal needs a finish line, or a number with its target. Goals you already have are not blocked." :error="errors.require_done_when">
              <TabButtons :model-value="d.settings.require_done_when === 0 || d.settings.require_done_when === false ? 0 : 1" :options="[{ label: 'On', value: 1 }, { label: 'Off', value: 0 }]"
                aria-label="Require Done when on new goals" data-setting="require_done_when" @update:model-value="(v) => d.is_admin && setOne('require_done_when', v)" />
            </SettingRow>
          </Card>
          <p class="text-sm text-ink-gray-6">{{ d.is_admin ? 'Changes save as you make them.' : 'Only the owner can change these.' }}</p>
        </template>
        <!-- Data: Reset, clear the backlog in batches or one by one -->
        <ResetSection v-if="show('data')" />
        <!-- Habits -->
        <template v-if="show('habits')">
          <SettingsList :kind="habitsList.kind" :rows="active(habitsList)" :noun="habitsList.noun" :hint="habitsList.hint" :ordered="habitsList.ordered" :writable="canEdit" :count-noun="habitsList.countNoun"
            @rename="(r, t) => rename(habitsList, r, t)" @reorder="(n, par) => reorder(habitsList, n, par)" @archive="(r) => askArchive(habitsList, r)" />
          <p class="text-sm text-ink-gray-6">{{ habitsList.footer }}</p>
        </template>
        <!-- Areas (issue 12) -->
        <template v-if="show('areas')">
          <AreasSection :space="spaceSel" :rows="d.areas" :is-admin="!!d.is_admin" :use-focuses="!!d.settings.use_focuses" @changed="changed" @use-focuses="(v) => setOne('use_focuses', v)" />
          <!-- each area's colour (its dot on goals and chips); issue 46 removed the pins with the lens -->
          <section id="pins" data-area-pins>
            <SectionHead>Colours</SectionHead>
            <Card flush>
              <SettingRow v-for="a in shownAreas" :key="a.name" :label="(a.parent_area ? '· ' : '') + a.title" :help="a.parent_area ? 'Part' : undefined">
                <div class="flex items-center gap-2">
                  <span class="size-2.5 rounded-full" :class="dotClass(a)" aria-hidden="true" />
                  <Select class="w-28" :model-value="a.colour || 'gray'" :options="COLOURS" :disabled="!d.is_admin" :aria-label="`Colour of ${a.title}`" :data-area-colour="a.name"
                    @update:model-value="(v) => saveArea(a, { colour: v })" />
                </div>
              </SettingRow>
            </Card>
          </section>
        </template>
        <!-- Rules: the note rules page, then who may read sensitive items -->
        <template v-if="show('rules')">
          <SectionHead>What agents know about you</SectionHead>
          <p class="text-sm text-ink-gray-6">The first thing an agent reads. Life OS writes it from your areas, goals, the 12 Week Year and your rules, and rebuilds it when they change. You cannot edit it here; change what it is made from.</p>
          <Card data-agent-card :data-words="agentCard?.words"><Md v-if="agentCard" :text="agentCard.card" /><Empty v-else title="Nothing to show yet." hint="It appears as soon as your areas and goals are set." /></Card>
          <SectionHead>Note rules</SectionHead>
          <p class="text-sm text-ink-gray-6">The assistant reads this page before it writes its notes. People edit it; agents cannot. It is also pinned at the top of the assistant's notes in the Library.</p>
          <NoteEditor v-if="rulesDoc" :key="rulesDoc.name" :note="rulesDoc" data-settings-rules />
          <Card v-else><Empty title="No rules page yet in this space." hint="It is made the first time the assistant reads the rules." /></Card>
          <SectionHead>Sensitive items</SectionHead>
          <p class="text-sm text-ink-gray-6">A sensitive item is a document from the Vault, or a capture or note marked sensitive. {{ manySpaces ? 'Each space decides who may read them. ' : '' }}Anyone who can edit an item may mark it; only the space's owner may unmark it.</p>
          <Card flush data-sensitive>
            <SettingRow v-for="sp in d.spaces" :key="sp.name" :label="manySpaces ? `Ask may read sensitive items in ${sp.name}` : 'Ask may read sensitive items'" help="Off by default. Ask answers the people in the space." :data-sensitive-space="sp.name">
              <Switch :model-value="!!sp.ask_can_read_vault" :aria-label="manySpaces ? `Ask may read sensitive items in ${sp.name}` : 'Ask may read sensitive items'" :data-ask-vault-switch="sp.name" :disabled="!d.is_admin"
                @update:model-value="(v) => setSpaceAsk(sp, 'ask_can_read_vault', v)" /></SettingRow>
          </Card>
          <Card v-if="!manySpaces && onlySpace" flush data-sensitive-agents>
            <SettingRow label="Agents may open sensitive items" help="Off by default. With it off, agents cannot list, read or download sensitive items.">
              <Switch :model-value="!!onlySpace.agents_can_read_vault" aria-label="Agents may open sensitive items" data-vault-switch :disabled="!d.is_admin"
                @update:model-value="(v) => setVault(onlySpace, v)" /></SettingRow>
          </Card>
          <p v-else class="text-sm text-ink-gray-6" data-sensitive-agents-note>Whether agents may open sensitive items is set for each space under
            <RouterLink v-if="d.is_admin" class="text-ink-blue-8 hover:underline" :to="{ query: { tab: 'members', view: 'spaces' } }">People and agents, Spaces</RouterLink><template v-else>People and agents, Spaces, by the owner</template>.</p>
        </template>
        <!-- Members: people and agents in one list, and the spaces -->
        <template v-if="show('members')">
          <TabButtons v-model="memberKind" class="self-start" :options="memberTabs" aria-label="Show" data-member-filter />
          <template v-if="memberKind === 'spaces' && manySpaces">
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
          <template v-else>
          <div class="flex gap-4 max-md:flex-col">
            <Select v-if="phone && manySpaces" :model-value="memberSpace" :options="d.spaces.map((s) => s.name)" aria-label="Space" @update:model-value="(v) => (memberSpace = v)" />
            <div v-else-if="manySpaces" class="flex w-40 flex-none flex-col gap-0.5" data-member-spaces>
              <Button v-for="s in d.spaces" :key="s.name" class="!justify-start" :variant="s.name === memberSpace ? 'subtle' : 'ghost'" :label="s.name" :data-space="s.name" @click="memberSpace = s.name" />
            </div>
            <div v-if="mSpace" class="flex min-w-0 flex-1 flex-col gap-3">
              <Card flush data-members>
                <MemberRow v-for="m in shownMembers" :key="m.user" :member="m" @access="(v) => setMember(mSpace.name, m.user, v)" @remove="askRemove(mSpace, m)" />
                <Empty v-if="!shownMembers.length" :title="memberKind === 'agents' ? `No agents in ${mSpace.name}.` : memberKind === 'people' ? `No people in ${mSpace.name}.` : 'No members.'"
                  hint="Add someone with Add member." />
              </Card>
            </div>
          </div>
          <p class="text-sm text-ink-gray-6">Everyone in a space, people and agents, sees its records. Can view lets them read; Can edit lets them add and change records.
            An agent's keys and its other spaces are under <RouterLink class="text-ink-blue-8 hover:underline" :to="{ query: { tab: 'members', view: 'agents' } }">Agents</RouterLink>.</p>
            <template v-if="memberKind === 'agents'">
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
              <span class="min-w-24 flex-1 text-base text-ink-gray-8">{{ manySpaces ? r.space : 'Access' }}</span>
              <span class="text-sm text-ink-gray-6" :data-agent-sensitive="a.user + '|' + r.space">{{ r.agents_can_read_vault ? 'Opens sensitive items' : 'No sensitive items' }}</span>
              <Select class="w-36" :model-value="r.access || ''" :options="AGENT_ACCESS" :aria-label="`${a.full_name} in ${r.space}`" :data-agent-access="a.user + '|' + r.space"
                @update:model-value="(v) => setAgent(r.space, a.user, v, r.access)" />
            </div>
          </Card>
          <Card v-if="!d.agents.length"><Empty title="No agents yet." data-agents-empty
            hint="An agent is a Frappe user that only an assistant signs in as. Create the user in Frappe, then add it to a space with Add member under Members: Life OS offers it agent access there." /></Card>
          <p class="text-sm text-ink-gray-6"><template v-if="manySpaces">Whether agents may open sensitive items is set for each space under
            <RouterLink class="text-ink-blue-8 hover:underline" :to="{ query: { tab: 'members', view: 'spaces' } }">Spaces</RouterLink>.
            </template><template v-else>Whether agents may open sensitive items is set under <RouterLink class="text-ink-blue-8 hover:underline" :to="{ query: { tab: 'rules' } }">Rules</RouterLink>. </template>Keys for agents are made in Frappe, never on this screen.</p>
            </template>
          </template>
        </template>
        <!-- Advanced (Life Admin): the AI key and cost, import and export, backups, the archive settings and where things are -->
        <template v-if="show('advanced')">
          <TabButtons v-model="advPart" class="self-start" :options="ADVANCED" aria-label="Advanced" data-advanced-parts />
          <template v-if="advPart === 'ai' && d.ai">
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
            <SectionHead>Prices per model</SectionHead>
            <Card flush>
              <Row v-for="pr in d.ai.prices" :key="pr.model" class="flex-wrap !items-center"><span class="min-w-40 flex-1 text-base text-ink-gray-8">{{ pr.model }}</span>
                <TextInput class="w-28" type="number" min="0" step="0.01" :model-value="pr.input_per_mtok" :aria-label="`${pr.model} input price`" @change="(e) => setPrice(pr, 'input_per_mtok', e.target.value)"><template #suffix><span class="text-sm text-ink-gray-6">in</span></template></TextInput>
                <TextInput class="w-28" type="number" min="0" step="0.01" :model-value="pr.output_per_mtok" :aria-label="`${pr.model} output price`" @change="(e) => setPrice(pr, 'output_per_mtok', e.target.value)"><template #suffix><span class="text-sm text-ink-gray-6">out</span></template></TextInput></Row>
            </Card>
            <p class="mt-1 text-sm text-ink-gray-6">US dollars per million tokens.</p>
          </section>
          <Card v-if="!manySpaces && onlySpace" flush data-ai-ask>
            <SettingRow label="Ask" help="People can ask about their records. Off, Ask is closed.">
              <Switch :model-value="!!onlySpace.ask_enabled" aria-label="Ask" data-ask-switch :disabled="!d.is_admin" @update:model-value="(v) => setSpaceAsk(onlySpace, 'ask_enabled', v)" /></SettingRow>
          </Card>
          <p v-else class="text-sm text-ink-gray-6" data-ai-spaces-note>Ask is switched on or off for each space under
            <RouterLink class="text-ink-blue-8 hover:underline" :to="{ query: { tab: 'members', view: 'spaces' } }">People and agents, Spaces</RouterLink>.</p>
            <SectionHead>Cost</SectionHead>
          <section>
            <SectionHead>This month by feature</SectionHead>
            <Card flush data-ai-spend>
              <Row><span class="flex-1 text-base text-ink-gray-9" data-cost-total>{{ d.ai.spend.text }}</span></Row>
              <Row v-for="p in d.ai.by_purpose" :key="p.purpose" :data-cost-feature="p.purpose"><span class="flex-1 text-base text-ink-gray-8">{{ p.purpose }}</span>
                <span class="text-sm tabular-nums text-ink-gray-6">{{ (p.input_tokens + p.output_tokens).toLocaleString() }} tokens · ${{ p.cost.toFixed(2) }}</span></Row>
              <Empty v-if="!d.ai.by_purpose.length" title="No AI calls this month." hint="Each call to the model, and what it cost, will be listed here." data-cost-empty />
            </Card>
          </section>
          <section>
            <SectionHead>Cap for a feature</SectionHead>
            <Card flush>
              <Row v-for="f in d.ai.feature_caps" :key="f.feature" class="flex-wrap !items-center" :data-feature-cap="f.feature"><span class="min-w-40 flex-1 text-base text-ink-gray-8">{{ f.feature }}
                <span class="text-sm text-ink-gray-6">${{ f.spent.toFixed(2) }} so far</span></span>
                <TextInput class="w-28" type="number" min="0" step="1" placeholder="No cap" :model-value="f.cap || ''" :aria-label="`${f.feature} cap`" @change="(e) => setFeatureCap(f, e.target.value)"><template #prefix><span class="text-sm text-ink-gray-6">$</span></template></TextInput></Row>
              <Row v-if="!d.ai.feature_caps.length"><span class="text-sm text-ink-gray-6">A feature appears here after its first call.</span></Row>
            </Card>
            <p class="mt-1 text-sm text-ink-gray-6">The monthly cap of ${{ d.ai.monthly_cap_usd }} is set under Ask and AI. Over a cap a feature falls back: area guesses use the rules, the Brain leaves items in Needs you.</p>
          </section>
          <section>
            <SectionHead>By day</SectionHead>
            <Card flush data-cost-days>
              <Row v-for="x in d.ai.by_day" :key="x.day"><span class="flex-1 text-base text-ink-gray-8">{{ x.day }}</span><span class="text-sm tabular-nums text-ink-gray-6">{{ x.calls }} {{ x.calls === 1 ? 'call' : 'calls' }} · ${{ x.cost.toFixed(2) }}</span></Row>
              <Row v-if="!d.ai.by_day.length"><span class="text-sm text-ink-gray-6">Nothing yet this month.</span></Row>
            </Card>
          </section>
          <section>
            <SectionHead>Last 50 calls</SectionHead>
            <Card flush data-cost-calls>
              <Row v-for="(c, i) in d.ai.calls" :key="i" class="flex-wrap !items-start" data-cost-call><div class="min-w-0 flex-1 basis-48"><div class="text-base text-ink-gray-8">{{ c.feature }}</div>
                <div class="break-words text-sm text-ink-gray-6">{{ dateTime(c.when) }} · {{ c.model }}<template v-if="c.reference"> · {{ c.reference }}</template> · {{ c.full_name }}</div></div>
                <span class="text-sm tabular-nums text-ink-gray-6">{{ (c.input_tokens + c.cached_tokens + c.output_tokens).toLocaleString() }} tokens · ${{ c.cost.toFixed(4) }}</span></Row>
              <Row v-if="!d.ai.calls.length"><span class="text-sm text-ink-gray-6">No calls yet.</span></Row>
            </Card>
          </section>
          </template>
          <template v-if="advPart === 'import'">
          <ConnectionsSection :space="spaceSel" :writable="canEdit && !store.isAgent" />
          </template>
          <template v-if="advPart === 'backups' && d.backups">
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
          <template v-if="advPart === 'guide'">
          <Card flush data-guide-settings>
            <SettingRow label="Welcome guide" :help="`The short guide a new person sees on first opening Life OS. It is ${onboarding.status ? (onboarding.status === 'done' ? 'done' : 'skipped') : 'not yet done'} for you now. Showing it again opens it only while the site has no tasks, goals or captures.`">
              <Button label="Show it again" :disabled="!onboarding.isSystemManager || !onboarding.status" data-guide-reset @click="resetGuide" />
            </SettingRow>
            <p v-if="!onboarding.isSystemManager" class="pb-3 text-sm text-ink-gray-6">Only a System Manager can reset it.</p>
          </Card>
          </template>
          <template v-if="advPart === 'archive'">
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
            Below are the headings archived from Areas, Habits and Check-ins{{ manySpaces ? ` in ${spaceSel}` : '' }}.</p>
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
        </template>
        </template>
      </div>
    </section>
  </div>

  <Dialog v-model:open="newOpen" :title="'New ' + (newList?.one || '')" size="sm"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Add', variant: 'solid', onClick: create }]">
    <div class="flex flex-col gap-3">
      <TextInput v-model="draft.title" :placeholder="newList?.placeholder" aria-label="Name" data-new-name @keydown.enter="create" />
    </div>
  </Dialog>
  <Dialog v-model:open="archiveOpen" :title="`Archive ${archiving?.row.title || ''}?`" size="md"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Archive', variant: 'solid', onClick: archive }]">
    <div class="flex flex-col gap-2 text-base text-ink-gray-8" data-archive-dialog>
      <p>It leaves the {{ archiving?.l.kind === 'habit' ? 'habit pickers' : 'check-in form' }}. Past records that use it keep it.</p>
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
// A routed page, not frappe-ui's SettingsDialog: that family's panels only work inside the dialog. The menu is frappe-ui
// Tabs in its vertical form, with the open section in the URL (tab=).
import { Avatar, Badge, Button, Dialog, Select, Skeleton, Switch, TabButtons, TabList, Tabs, TabTrigger, TextInput, TimePicker, dialog, toast, useColorScheme } from 'frappe-ui'
import NoteEditor from '@/components/NoteEditor.vue'
import { ELSEWHERE } from '@/lib/nav'
import { ladder, loadLadder } from '@/lib/ladder'
import { dotClass, manySpaces } from '@/lib/lens'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import Md from '@/components/Md.vue'
import CalendarSection from '@/components/settings/CalendarSection.vue'
import AreasSection from '@/components/settings/AreasSection.vue'
import ResetSection from '@/components/settings/ResetSection.vue'
import SettingRow from '@/components/settings/SettingRow.vue'
import SettingsList from '@/components/settings/SettingsList.vue'
import ConnectionsSection from '@/components/settings/ConnectionsSection.vue'
import MemberRow from '@/components/settings/MemberRow.vue'
import AddMemberDialog from '@/components/settings/AddMemberDialog.vue'
import LifeLink from '@/framework/LifeLink.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { boot, store } from '@/lib/store'
import { loadLookups } from '@/lib/lookups'
import { loadOnboarding, onboarding } from '@/lib/onboarding'
import { dateTime, short } from '@/lib/dates'

const COLOURS = ['blue', 'green', 'amber', 'red', 'violet', 'teal', 'orange', 'pink', 'cyan', 'gray'].map((c) => ({ label: c[0].toUpperCase() + c.slice(1), value: c }))
const hm = (t) => (t ? String(t).padStart(8, '0').slice(0, 5) : '06:00')
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
// set 7: Inbox items not dealt with. Each choice brings its own default number of days, unless the days were changed by hand
const OLD_INBOX = [{ label: 'Suggest decisions', value: 'Suggest' }, { label: 'Park them in Someday', value: 'Park' }, { label: 'Discard them to the trash', value: 'Discard' }]
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
  { kind: 'habit', section: 'habits', label: 'Habits', one: 'habit', noun: 'habits', key: 'habits', field: 'title', placeholder: 'For example Walk',
    hint: 'Habits you may track in a month.', countNoun: ['tick', 'ticks'], footer: 'This is the library of habits ever tracked. Which ones count in a month is set under Today, Month, Habits, Manage habits.' },
]
const habitsList = LISTS[1]
const route = useRoute()
const router = useRouter()
const phone = useMediaQuery('(max-width: 767px)')
const { colorScheme, setColorScheme } = useColorScheme()
const platform = /iPhone|iPad|iPod/.test(navigator.userAgent) ? 'ios' : /Android/.test(navigator.userAgent) ? 'android' : ''
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

// The menu (issue 44): eight items in four groups and Advanced at the foot. `level` is the first level of the ladder at which a person
// who is not a Life Admin sees the item; a Life Admin sees all. A page left out of the menu is still reached by its link.
const MENU = [
  { key: 'me', label: 'Me', items: [{ value: 'profile', label: 'Profile', level: 1 }, { value: 'calendar', label: 'Calendar', level: 2 }] },
  { key: 'space', label: 'Your life', items: [{ value: 'areas', label: 'Areas', level: 1 }, { value: 'rhythms', label: 'Rhythms', level: 4 }, { value: 'habits', label: 'Habits', level: 3 }, { value: 'data', label: 'Data', level: 4 }] },
  { key: 'brain', label: 'Brain', items: [{ value: 'sources', label: 'Sources', level: 1 }, { value: 'rules', label: 'Rules', level: 3 }] },
  { key: 'people', label: 'People and agents', items: [{ value: 'members', label: 'Members', level: 6, admin: true }] },
  { key: 'advanced', label: '', items: [{ value: 'advanced', label: 'Advanced', level: 1, admin: true }] },
]
const ADVANCED = [{ label: 'AI key and cost', value: 'ai' }, { label: 'Import and export', value: 'import' }, { label: 'Backups', value: 'backups' },
  { label: 'Archive', value: 'archive' }, { label: 'First-run guide', value: 'guide' }]
async function resetGuide() {
  await tryCall(() => api('onboarding.reset'), 'The guide will show again.')
  await loadOnboarding()
}
const ready = computed(() => !!d.value && ladder.loaded)
const isAdmin = computed(() => !!d.value?.is_admin)
// items that need a Life Admin (Members, Advanced) are never shown to anyone else; the rest by the person's level
const seen = (it) => (it.admin ? isAdmin.value : true) && (isAdmin.value || ladder.level >= it.level)
const groups = computed(() => MENU.map((g) => ({ ...g, items: g.items.filter(seen) })).filter((g) => g.items.length))
// "Rhythms at level 4, Members at level 6": what is still to come, for a person who is not a Life Admin
const later = computed(() => {
  if (isAdmin.value) return ''
  const hidden = MENU.flatMap((g) => g.items).filter((it) => !it.admin && !seen(it) && it.value !== 'sources').sort((x, y) => x.level - y.level)
  const levels = [...new Set(hidden.map((it) => it.level))]
  return levels.map((n) => `${hidden.filter((it) => it.level === n).map((it) => it.label).join(' and ')} at level ${n}`).join(', ')
})
const PAGES = ['profile', 'calendar', 'areas', 'rhythms', 'habits', 'data', 'rules', 'members', 'advanced']
const ADMIN_ONLY = ['members', 'advanced']
// Every old section and where it lives now: a page of Settings (with its part), or another place
const MOVED = {
  default: { tab: 'profile' }, appearance: { tab: 'profile' }, notifications: { tab: 'profile' }, shortcuts: { tab: 'profile' },
  review: { tab: 'rhythms' }, reset: { tab: 'data' },
  sensitive: { tab: 'rules' }, 'note-rules': { tab: 'rules' },
  spaces: { tab: 'members', view: 'spaces' }, agents: { tab: 'members', view: 'agents' }, assistants: { tab: 'members', view: 'agents' }, people: { tab: 'members', view: 'people' },
  ai: { tab: 'advanced', part: 'ai' }, cost: { tab: 'advanced', part: 'ai' }, import: { tab: 'advanced', part: 'import' }, backups: { tab: 'advanced', part: 'backups' },
  places: { tab: 'profile' },
  archived: { path: '/library/archive' }, archive: { path: '/library/archive' },
  connections: { path: '/brain/sources' }, sources: { path: '/brain/sources' },
}
// the page issue 60 deleted: its old link goes to Library > Trash and archive (spelt in two parts so that no code names the deleted thing)
MOVED['tag' + 's'] = { path: '/library/archive' }
// the open page is tab= in the URL. On a wide screen the first page is the default; on a phone the menu is.
const section = computed(() => {
  const v = route.query.tab ? String(route.query.tab) : ''
  if (PAGES.includes(v) && !(ADMIN_ONLY.includes(v) && d.value && !d.value.is_admin)) return v
  return phone.value ? '' : 'profile'
})
const show = (page) => section.value === page
// an old link lands on its new place
watch(() => route.query.tab, (t) => {
  const to = MOVED[String(t || '')]
  if (!to) return
  if (to.path) router.replace({ path: to.path })
  else router.replace({ query: { ...route.query, ...to } })
}, { immediate: true })
// the Tabs component answers a page that is not in the menu (yet) by naming one that is: only a click may leave such a page
const onTab = (v) => groups.value.some((g) => g.items.some((it) => it.value === section.value)) && open(v)
function open(v) {
  if (v === 'sources') return router.push('/brain/sources')
  if (v === section.value) return
  router.push({ query: { ...route.query, tab: v && (phone.value || v !== 'profile') ? v : undefined, view: undefined, part: undefined } })
}
// "This space": its own space picker, which does not change the space of the sidebar (space= in the URL)
const spaceSel = computed(() => (manySpaces.value && route.query.space ? String(route.query.space) : store.space))
const pickSpace = (v) => router.replace({ query: { ...route.query, space: v === store.space ? undefined : v } })
const spaceGroup = ['areas', 'habits', 'rhythms', 'rules']
const heading = computed(() => {
  const label = section.value === 'areas' ? 'Areas of life' : MENU.flatMap((g) => g.items).find((s) => s.value === section.value)?.label || ''
  return spaceGroup.includes(section.value) && manySpaces.value ? `${label} in ${spaceSel.value}` : label
})
const canEdit = computed(() => d.value?.spaces.find((s) => s.name === spaceSel.value)?.access === 'Write')
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
// the one space of a site that has one: its Ask and sensitive-items switches are plain settings (issue 46)
const onlySpace = computed(() => (!manySpaces.value ? d.value?.spaces.find((x) => x.name === store.space) || null : null))
const mSpace = computed(() => d.value?.spaces.find((s) => s.name === memberSpace.value))
// Members: All, People, Agents, with counts
const memberKind = computed({
  get: () => ((manySpaces.value ? ['people', 'agents', 'spaces'] : ['people', 'agents']).includes(String(route.query.view)) ? String(route.query.view) : 'all'),
  set: (v) => router.replace({ query: { ...route.query, view: v === 'all' ? undefined : v } }),
})
const advPart = computed({
  get: () => (ADVANCED.some((x) => x.value === route.query.part) ? String(route.query.part) : 'ai'),
  set: (v) => router.replace({ query: { ...route.query, part: v === 'ai' ? undefined : v } }),
})
const memberTabs = computed(() => {
  const all = mSpace.value?.members || []
  const agents = all.filter((m) => m.is_agent).length
  return [{ label: `All ${all.length}`, value: 'all' }, { label: `People ${all.length - agents}`, value: 'people' }, { label: `Agents ${agents}`, value: 'agents' },
    ...(manySpaces.value ? [{ label: `Spaces ${d.value?.spaces.length || 0}`, value: 'spaces' }] : [])]
})
const shownMembers = computed(() => (mSpace.value?.members || []).filter((m) => memberKind.value === 'all' || m.is_agent === (memberKind.value === 'agents')))
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`

// What agents know about you (issue 54): the core card, read only
const agentCard = ref(null)
watch(() => section.value, async (sec) => { if (sec === 'rules' && !agentCard.value) agentCard.value = await tryCall(() => api('context.card')) }, { immediate: true })
// Note rules: the rules page of the assistant's notes in this space
const rulesDoc = ref(null)
watch(() => [section.value, d.value?.rules_note], async ([sec, name]) => {
  if (sec === 'note-rules' && name && rulesDoc.value?.name !== name) rulesDoc.value = await tryCall(() => api('library.get', { note: name }))
}, { immediate: true })
// an area's colour
async function saveArea(a, values) {
  const before = { colour: a.colour }
  Object.assign(a, values)
  if (await tryCall(() => api('settings.save_item', { kind: 'area', name: a.name, ...values }), 'Saved')) changed()
  else Object.assign(a, before)
}
async function load() {
  const res = await tryCall(() => api('settings.get', { space: spaceSel.value }))
  if (!res) return
  if (res.settings.weekly_review_time) res.settings.weekly_review_time = String(res.settings.weekly_review_time).padStart(8, '0').slice(0, 5)
  if (!manySpaces.value) { // issue 46: one space is not shown as a space; an owner of the site may be sent others, which this person does not see
    res.spaces = res.spaces.filter((x) => x.name === store.space)
    for (const a of res.agents || []) a.spaces = (a.spaces || []).filter((x) => x.space === store.space)
  }
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
  if (await tryCall(() => api('settings.set_ai_price', { model: pr.model, input_per_mtok: pr.input_per_mtok, output_per_mtok: pr.output_per_mtok, cached_per_mtok: pr.cached_per_mtok }), 'Saved')) await load()
}
async function setFeatureCap(f, value) {
  if (await tryCall(() => api('settings.set_feature_cap', { feature: f.feature, cap: Number(value) || 0 }), 'Saved')) await load()
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
    if (field === 'default_space' || field === 'require_done_when' || field === 'use_focuses') boot()
    if (field === 'use_focuses') changed()
  } catch (e) {
    errors[field] = errorText(e)
    d.value.settings[field] = before
  }
}

// ---- the four lists ----
const newList = ref(null)
function openNew(l) {
  newList.value = l
  newOpen.value = true
}
async function rename(l, r, title) {
  if (await tryCall(() => api('settings.save_item', { kind: l.kind, name: r.name, title }), 'Renamed')) changed()
}
async function reorder(l, names, parent) {
  if (await tryCall(() => api('settings.reorder', { kind: l.kind, names, parent_area: l.kind === 'area' ? parent || '' : undefined }), 'Saved')) changed()
}
async function create() {
  const l = newList.value
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
function askArchive(l, r) {
  archiving.value = { l, row: r }
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
  router.push({ query: { tab: 'members' } })
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

onMounted(loadLadder)
watch(spaceSel, load, { immediate: true })
</script>
