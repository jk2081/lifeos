// First run (issue 49): whether the guide should open, and whether the site is still empty (nothing yet to show on Today).
import { reactive } from 'vue'
import { api } from './api'

export const onboarding = reactive({ loaded: false, show: false, empty: false, status: null, isSystemManager: false, fullName: '', timeZone: '' })

export async function loadOnboarding() {
  try {
    const s = await api('onboarding.state')
    Object.assign(onboarding, { loaded: true, show: s.show, empty: s.empty, status: s.status, isSystemManager: s.is_system_manager,
      fullName: s.full_name, timeZone: s.time_zone })
  } catch (e) { /* the guide is not worth an error */ }
}

// record that the guide is over ("done" or "skipped"): it does not open again
export async function finishOnboarding(status) {
  onboarding.show = false
  try { await api('onboarding.complete', { status }) } catch (e) { /* kept next time */ }
  await loadOnboarding()
}
