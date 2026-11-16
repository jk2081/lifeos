#!/bin/bash
# (Re)create the throwaway site acceptance.localhost on the local bench, with the test users, the seed and the demo data.
# tools/acceptance.mjs runs against it (http://localhost:19000), so lifeos.localhost stays clean for the owner.
#   scripts/acceptance-site.sh          fresh site from a saved snapshot (made on first use)
#   scripts/acceptance-site.sh --new    drop the snapshot and build the site from scratch
# The test users' password is read from the git-ignored .env and passed in the environment, never printed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SITE=acceptance.localhost
PW="$(grep '^LIFEOS_DEV_PASSWORD=' "$ROOT/.env" | cut -d= -f2-)"
SNAPDIR=/home/frappe/acceptance-snapshot
SNAP="$SNAPDIR/snapshot.sql.gz"
B="docker exec -e LIFEOS_PW=$PW lifeos-bench bash -lc"
[ "${1:-}" = "--new" ] && $B "rm -rf $SNAPDIR"
if $B "test -f $SNAP" 2>/dev/null && $B "test -d ~/frappe-bench/sites/$SITE"; then
  $B "cd ~/frappe-bench && bench --site $SITE --force restore $SNAP --db-root-password lifeos-local-root >/tmp/acc-site.log 2>&1 && bench --site $SITE migrate >>/tmp/acc-site.log 2>&1 && bench --site $SITE clear-cache >/dev/null 2>&1"
else
  $B "cd ~/frappe-bench && bench drop-site $SITE --force --no-backup --db-root-password lifeos-local-root >/dev/null 2>&1 || true
      bench new-site $SITE --db-root-password lifeos-local-root --admin-password \"\$(head -c 24 /dev/urandom | base64)\" --install-app lifeos >/tmp/acc-site.log 2>&1
      bench --site $SITE set-config allow_tests true >/dev/null
      bench --site $SITE execute lifeos.devtools.prepare_site >>/tmp/acc-site.log 2>&1
      bench --site $SITE execute lifeos.devtools.setup_users --kwargs \"{'password': '\$LIFEOS_PW'}\" >>/tmp/acc-site.log 2>&1
      bench --site $SITE execute lifeos.seed.load >>/tmp/acc-site.log 2>&1
      bench --site $SITE execute lifeos.demo.load >>/tmp/acc-site.log 2>&1
      rm -rf $SNAPDIR && mkdir -p $SNAPDIR && bench --site $SITE backup --backup-path $SNAPDIR >>/tmp/acc-site.log 2>&1
      mv \$(ls $SNAPDIR/*-database.sql.gz | head -1) $SNAP && rm -f $SNAPDIR/*.json"
fi
# Its own web server on container port 9000 (host 19000, the port the compose file maps and nothing else uses), since
# `bench serve` on 8000 serves the default site only. Restarted each time so it runs the current code.
$B "pkill -f 'serve --port [9]000' || true"
docker exec -d lifeos-bench bash -lc "cd ~/frappe-bench && bench --site $SITE serve --port 9000 --noreload > /tmp/serve-acceptance.log 2>&1"
for i in $(seq 1 60); do curl -s -o /dev/null -m 2 http://localhost:19000/api/method/ping && break; sleep 1; done
echo "acceptance.localhost ready at http://localhost:19000"
