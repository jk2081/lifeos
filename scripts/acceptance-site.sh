#!/bin/bash
# (Re)create the throwaway site acceptance.localhost on the local bench, with the test users and the demo data.
# tools/acceptance.mjs runs against it (http://localhost:19000), so lifeos.localhost stays clean for the owner.
#   scripts/acceptance-site.sh          fresh site from a saved snapshot (made on first use)
#   scripts/acceptance-site.sh --new    drop the snapshot and build the site from scratch
# The bench is reached through tools/bench.sh: the Docker bench by default, a bench folder on this machine with
# LIFEOS_BENCH_CMD=local and LIFEOS_BENCH_PATH (GitHub Actions). The test users' password is LIFEOS_DEV_PASSWORD from
# the environment, else from the git-ignored .env; it is passed in the environment, never printed. The database root
# password is LIFEOS_DB_ROOT_PASSWORD, else the Docker stack's.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SITE=acceptance.localhost
LIFEOS_PW="${LIFEOS_DEV_PASSWORD:-}"
[ -n "$LIFEOS_PW" ] || LIFEOS_PW="$(grep '^LIFEOS_DEV_PASSWORD=' "$ROOT/.env" | cut -d= -f2-)"
export LIFEOS_PW
# expanded on the bench, from the variable tools/bench.sh passes by name
DBROOT='"${LIFEOS_DB_ROOT_PASSWORD:-lifeos-local-root}"'
SNAPDIR='$HOME/acceptance-snapshot'
SNAP="$SNAPDIR/snapshot.sql.gz"
B="$ROOT/tools/bench.sh"
# the Docker bench serves on container port 9000, which the compose file maps to host port 19000; a local bench on 19000
PORT=9000
[ "${LIFEOS_BENCH_CMD:-docker}" = local ] && PORT=19000
[ "${1:-}" = "--new" ] && $B "rm -rf $SNAPDIR"
if $B "test -f $SNAP" 2>/dev/null && $B "test -d sites/$SITE"; then
  $B "bench --site $SITE --force restore $SNAP --db-root-password $DBROOT >/tmp/acc-site.log 2>&1 && bench --site $SITE migrate >>/tmp/acc-site.log 2>&1 && bench --site $SITE clear-cache >/dev/null 2>&1"
else
  $B "bench drop-site $SITE --force --no-backup --db-root-password $DBROOT >/dev/null 2>&1 || true
      bench new-site $SITE --db-root-password $DBROOT --admin-password \"\$(head -c 24 /dev/urandom | base64)\" --install-app lifeos >/tmp/acc-site.log 2>&1
      bench --site $SITE set-config allow_tests true >/dev/null
      bench --site $SITE execute lifeos.tools.devtools.prepare_site >>/tmp/acc-site.log 2>&1
      bench --site $SITE execute lifeos.tools.devtools.setup_users --kwargs \"{'password': '\$LIFEOS_PW'}\" >>/tmp/acc-site.log 2>&1
      bench --site $SITE execute lifeos.tools.demo.load >>/tmp/acc-site.log 2>&1
      rm -rf $SNAPDIR && mkdir -p $SNAPDIR && bench --site $SITE backup --backup-path $SNAPDIR >>/tmp/acc-site.log 2>&1
      mv \$(ls $SNAPDIR/*-database.sql.gz | head -1) $SNAP && rm -f $SNAPDIR/*.json"
fi
# issue 58: process-capture ships on; this site starts like one with an agent working the Inbox
$B "bench --site $SITE execute lifeos.tools.devtools.brain_off >/dev/null 2>&1"
# GETs to Life OS methods run read-only here, so a read that writes fails the run (lifeos/web/strict_get.py)
$B "bench --site $SITE set-config -p lifeos_strict_get 1 >/dev/null"
# issue 57: checks that predate the retirement of the Open goal still make one through the API; the site itself refuses it otherwise
$B "bench --site $SITE set-config -p lifeos_allow_open_goals 1 >/dev/null"
# set 8: a fixture calendar stands in for Google here
$B "bench --site $SITE set-config -p lifeos_fake_calendar 1 >/dev/null"
# issue 86: a fake Gmail and a fake Google stand in for the real ones (lifeos/mail/fake.py)
$B "bench --site $SITE set-config -p lifeos_fake_gmail 1 >/dev/null"
# issue 88: a fake Microsoft Graph too (lifeos/mail/fake.py)
$B "bench --site $SITE set-config -p lifeos_fake_microsoft 1 >/dev/null"
# the rhythm banners' clock may be moved here (today.get's `at`), and only here (UX fixes, set 6)
$B "bench --site $SITE set-config -p lifeos_test_clock 1 >/dev/null"
# Its own web server (host port 19000, which nothing else uses), since `bench serve` on 8000 serves the default site
# only. Restarted each time so it runs the current code.
$B "pkill -f 'serve --port [${PORT:0:1}]${PORT:1}' || true"
$B -d "bench --site $SITE serve --port $PORT --noreload > /tmp/serve-acceptance.log 2>&1"
# a background worker, for jobs such as the chat export import (it serves the queues of every site on the bench)
$B "pkill -f 'frappe.utils.bench_helper frappe worke[r]' || true"
$B -d "bench worker --queue long,default,short > /tmp/worker-acceptance.log 2>&1"
for i in $(seq 1 60); do curl -s -o /dev/null -m 2 http://localhost:19000/api/method/ping && break; sleep 1; done
echo "acceptance.localhost ready at http://localhost:19000"
