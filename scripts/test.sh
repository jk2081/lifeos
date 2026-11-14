#!/bin/bash
# Run the lifeos test suite on the local Docker bench and print a short summary.
#   scripts/test.sh                 all tests
#   scripts/test.sh test_m2_data_model   one module
MOD=""
[ -n "$1" ] && MOD="--module lifeos.tests.$1"
docker exec lifeos-bench bash -lc "cd ~/frappe-bench && bench --site lifeos.localhost run-tests --app lifeos $MOD 2>&1" > /tmp/lifeos-test.log
grep -E "✖|^(FAIL|ERROR):|^[A-Za-z_.]*(Error|Exception)[:(]|^Ran |^OK|^FAILED|AssertionError" /tmp/lifeos-test.log | grep -v Deprecation | head -${LINES_MAX:-40}
grep -q "^OK" /tmp/lifeos-test.log
