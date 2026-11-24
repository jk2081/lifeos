// First run (issue 49): whether the guide should open, and whether the site is still empty (nothing yet to show on Today).
import { reactive } from 'vue'
import { api } from './api'

// the step the person is on, kept for the visit to Connections and back (a sign-in with Google reloads the app)
export const STEP_KEY = 'lifeos-guide-step'

export const onboarding = reactive({ loaded: false, show: false, empty: false, status: null, isSystemManager: false, fullName: '', timeZone: '', callMe: '', aiSet: false, googleConnected: false, away: false })

export async function loadOnboarding() {
  try {
    const s = await api('onboarding.state')
    Object.assign(onboarding, { loaded: true, show: s.show, empty: s.empty, status: s.status, isSystemManager: s.is_system_manager,
      fullName: s.full_name, timeZone: s.time_zone, callMe: s.call_me, aiSet: s.ai_set, googleConnected: s.google_connected })
  } catch (e) { /* the guide is not worth an error */ }
}

// record that the guide is over ("done" or "skipped"): it does not open again
export async function finishOnboarding(status) {
  onboarding.show = false
  onboarding.away = false
  sessionStorage.removeItem(STEP_KEY)
  try { await api('onboarding.complete', { status }) } catch (e) { /* kept next time */ }
  await loadOnboarding()
}
