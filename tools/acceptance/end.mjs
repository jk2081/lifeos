// The clean-up checks and the scan that end every run (not a place: they check the site and the code, whichever place ran).
import { bench, check, execFileSync, must, path, root } from './context.mjs'

await check('END.1', "This run's records are removed from the acceptance site", async () => {
  const code = 'from lifeos.tools import devtools\nimport json\ndevtools.purge_test_debris(dry_run=0)\nd, st = devtools.find_test_debris()\nprint(json.dumps({k: len(v) for k, v in d.items()}))'
  let out
  try { out = bench(code) } catch (e) { out = bench(code) } // the purge is safe to repeat: a lock wait on a busy runner should not fail the run
  out = out.split('\n').pop()
  must(!Object.keys(JSON.parse(out)).length, 'left on the acceptance site: ' + out)
})

await check('END.2', 'No test debris on lifeos.localhost after the run', async () => {
  const out = bench('from lifeos.tools import devtools\nimport json\nd, st = devtools.find_test_debris()\nprint(json.dumps({k: len(v) for k, v in d.items()}))', 'lifeos.localhost').split('\n').pop()
  const d = JSON.parse(out)
  must(!Object.keys(d).length, 'debris on lifeos.localhost: ' + out)
})

await check('END.3', "Frappe's semgrep rules report no finding (tools/scan.sh)", async () => {
  try {
    execFileSync(path.join(root, 'tools/scan.sh'), { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
  } catch (e) {
    const lines = String(e.stdout || '').trim().split('\n')
    throw new Error('findings: ' + lines.slice(-3).join(' ').replace(/\s+/g, ' '))
  }
})
