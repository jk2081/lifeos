// A time zone as a person reads it: "India — Kolkata (GMT+5:30)" (issue 97). The browser knows the zone's offset but not its country, so the
// common zones carry theirs here; any other reads "<region> — <city>".
const COUNTRY = {
  'Asia/Kolkata': 'India', 'Asia/Calcutta': 'India', 'Asia/Dubai': 'United Arab Emirates', 'Asia/Singapore': 'Singapore', 'Asia/Hong_Kong': 'Hong Kong',
  'Asia/Tokyo': 'Japan', 'Asia/Seoul': 'South Korea', 'Asia/Shanghai': 'China', 'Asia/Karachi': 'Pakistan', 'Asia/Dhaka': 'Bangladesh',
  'Asia/Colombo': 'Sri Lanka', 'Asia/Kathmandu': 'Nepal', 'Asia/Bangkok': 'Thailand', 'Asia/Jakarta': 'Indonesia', 'Asia/Manila': 'Philippines',
  'Asia/Riyadh': 'Saudi Arabia', 'Asia/Tehran': 'Iran', 'Asia/Jerusalem': 'Israel', 'Asia/Kuala_Lumpur': 'Malaysia', 'Asia/Taipei': 'Taiwan',
  'Europe/London': 'United Kingdom', 'Europe/Dublin': 'Ireland', 'Europe/Paris': 'France', 'Europe/Berlin': 'Germany', 'Europe/Madrid': 'Spain',
  'Europe/Rome': 'Italy', 'Europe/Amsterdam': 'Netherlands', 'Europe/Zurich': 'Switzerland', 'Europe/Stockholm': 'Sweden', 'Europe/Moscow': 'Russia',
  'Europe/Istanbul': 'Turkey', 'Europe/Lisbon': 'Portugal', 'Europe/Athens': 'Greece',
  'Africa/Cairo': 'Egypt', 'Africa/Lagos': 'Nigeria', 'Africa/Nairobi': 'Kenya', 'Africa/Johannesburg': 'South Africa',
  'Australia/Sydney': 'Australia', 'Australia/Melbourne': 'Australia', 'Australia/Perth': 'Australia', 'Australia/Brisbane': 'Australia',
  'Pacific/Auckland': 'New Zealand', 'America/Sao_Paulo': 'Brazil', 'America/Argentina/Buenos_Aires': 'Argentina', 'America/Mexico_City': 'Mexico',
  'America/Toronto': 'Canada', 'America/Vancouver': 'Canada', 'America/New_York': 'United States', 'America/Chicago': 'United States',
  'America/Denver': 'United States', 'America/Los_Angeles': 'United States', 'America/Phoenix': 'United States', 'America/Anchorage': 'United States',
  'Pacific/Honolulu': 'United States',
}

// "GMT+5:30", "GMT-8", "GMT+0"
export function offsetOf(zone, at = new Date()) {
  try {
    const part = new Intl.DateTimeFormat('en', { timeZone: zone, timeZoneName: 'longOffset' }).formatToParts(at).find((p) => p.type === 'timeZoneName')?.value || 'GMT'
    const m = part.match(/GMT([+-])(\d{2}):(\d{2})/)
    if (!m) return 'GMT+0'
    return `GMT${m[1]}${Number(m[2])}${m[3] === '00' ? '' : ':' + m[3]}`
  } catch (e) { return 'GMT+0' }
}

export function zoneLabel(zone) {
  const parts = String(zone).split('/')
  const city = parts[parts.length - 1].replace(/_/g, ' ')
  const place = COUNTRY[zone] || (parts.length > 1 ? parts[0].replace(/_/g, ' ') : '')
  return `${place ? place + ' — ' : ''}${city} (${offsetOf(zone)})`
}

// the browser may name a zone by its old name
const CURRENT = { 'Asia/Calcutta': 'Asia/Kolkata', 'Asia/Katmandu': 'Asia/Kathmandu', 'Asia/Saigon': 'Asia/Ho_Chi_Minh', 'Asia/Rangoon': 'Asia/Yangon' }
export const currentZone = (zone) => CURRENT[zone] || zone
