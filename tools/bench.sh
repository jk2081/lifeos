#!/bin/bash
# Run a shell command in the bench folder: the one place the acceptance tooling reaches the bench.
#
#   tools/bench.sh 'bench --site acceptance.localhost migrate'     run and wait
#   tools/bench.sh -i 'cd sites && ../env/bin/python -'             pass this script's stdin to the command
#   tools/bench.sh -d 'bench --site acceptance.localhost serve'     start it in the background and return
#
# By default the command runs in the Docker bench on the owner's Mac (`docker exec lifeos-bench bash -lc`, in
# ~/frappe-bench; LIFEOS_BENCH names another container). With LIFEOS_BENCH_CMD=local it runs `bash -c` on this
# machine in the bench folder named by LIFEOS_BENCH_PATH (GitHub Actions). LIFEOS_PW and LIFEOS_DB_ROOT_PASSWORD, when
# set, are passed through by name, so they never appear in a process list or a log.
set -euo pipefail
STDIN=0
DETACH=0
while [ "$#" -gt 1 ]; do
  case "$1" in
    -i) STDIN=1; shift ;;
    -d) DETACH=1; shift ;;
    *) break ;;
  esac
done
[ "$#" -eq 1 ] || { echo "usage: tools/bench.sh [-i|-d] COMMAND" >&2; exit 2; }

if [ "${LIFEOS_BENCH_CMD:-docker}" = local ]; then
  [ -n "${LIFEOS_BENCH_PATH:-}" ] || { echo "LIFEOS_BENCH_CMD=local needs LIFEOS_BENCH_PATH" >&2; exit 2; }
  cd "$LIFEOS_BENCH_PATH"
  if [ "$DETACH" = 1 ]; then
    nohup bash -c "$1" </dev/null >/dev/null 2>&1 &
    exit 0
  fi
  [ "$STDIN" = 1 ] && exec bash -c "$1"
  exec bash -c "$1" </dev/null
fi

ARGS=()
[ -n "${LIFEOS_PW:-}" ] && ARGS+=(-e LIFEOS_PW)
[ -n "${LIFEOS_DB_ROOT_PASSWORD:-}" ] && ARGS+=(-e LIFEOS_DB_ROOT_PASSWORD)
[ "$STDIN" = 1 ] && ARGS+=(-i)
[ "$DETACH" = 1 ] && ARGS+=(-d)
exec docker exec ${ARGS[@]+"${ARGS[@]}"} "${LIFEOS_BENCH:-lifeos-bench}" bash -lc "cd ~/frappe-bench && $1"
