// Drawing code (the graph) needs plain rgb() values: frappe-ui tokens are oklch(), which canvas libraries do not parse.
// The value is read from the token's CSS variable and painted on a 1 px canvas, so both themes work.
let ctx = null
export function tokenColor(name) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name.startsWith('--') ? name : `--${name}`).trim()
  if (!value) return 'rgb(128, 128, 128)'
  ctx ||= Object.assign(document.createElement('canvas'), { width: 1, height: 1 }).getContext('2d', { willReadFrequently: true })
  ctx.clearRect(0, 0, 1, 1)
  ctx.fillStyle = value
  ctx.fillRect(0, 0, 1, 1)
  const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data
  return `rgb(${r}, ${g}, ${b})`
}
