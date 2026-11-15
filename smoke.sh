#!/usr/bin/env bash
# BasketryStitch smoke test: add -> list -> estimate against a throw-away log.
# Every step must exit 0 and the worked example must project 440.00 mm.
#
#     sh smoke.sh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PYTHON="${PYTHON:-python3}"
TOOL="$SCRIPT_DIR/basketrystitch.py"

WORKDIR=$(mktemp -d)
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT
LOG="$WORKDIR/smoke_log.json"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

expect_in() {
  haystack=$1
  needle=$2
  case "$haystack" in
    *"$needle"*) ;;
    *) fail "expected to find '$needle'" ;;
  esac
}

echo "1/6 add: 10-row sample, 100 mm before, 88 mm after"
out=$("$PYTHON" "$TOOL" add --log "$LOG" --name "Willow Coil" --reed-width 4 \
  --unit in --sample-rows 10 --row-height-before 100 --row-height-after 88) ||
  fail "add exited non-zero"
expect_in "$out" "Added entry 1: Willow Coil"
expect_in "$out" "reed width: 4.00 in (101.60 mm)"
echo "$out"

echo
echo "2/6 add: a second sample in centimetres"
out=$("$PYTHON" "$TOOL" add --log "$LOG" --name "Bulrush Tray" --reed-width 10 \
  --unit cm --sample-rows 8 --row-height-before 80 --row-height-after 72) ||
  fail "second add exited non-zero"
expect_in "$out" "Added entry 2: Bulrush Tray"
expect_in "$out" "10.00 cm (100.00 mm)"
echo "$out"

echo
echo "3/6 list: both entries in ascending id order"
out=$("$PYTHON" "$TOOL" list --log "$LOG") || fail "list exited non-zero"
expect_in "$out" "Willow Coil"
expect_in "$out" "Bulrush Tray"
expect_in "$out" "12.0%"
first=$(printf '%s' "$out" | grep -n "Willow Coil" | cut -d: -f1)
second=$(printf '%s' "$out" | grep -n "Bulrush Tray" | cut -d: -f1)
[ "$first" -lt "$second" ] || fail "list did not keep ascending id order"
echo "$out"

echo
echo "4/6 estimate --target-rows 50: must project 440.00 mm"
out=$("$PYTHON" "$TOOL" estimate --log "$LOG" --id 1 --target-rows 50) ||
  fail "estimate exited non-zero"
expect_in "$out" "per-row after: 8.80 mm"
expect_in "$out" "shrinkage: 12.0%"
expect_in "$out" "projected finished height: 440.00 mm"
echo "$out"

echo
echo "5/6 estimate --target-height 440: must project 50 rows"
out=$("$PYTHON" "$TOOL" estimate --log "$LOG" --id 1 --target-height 440) ||
  fail "estimate exited non-zero"
expect_in "$out" "projected rows: 50"
echo "$out"

echo
echo "6/6 a blank name is refused with exit code 2 and leaves the log intact"
before=$(cksum "$LOG")
set +e
"$PYTHON" "$TOOL" add --log "$LOG" --name "   " --reed-width 4 --sample-rows 10 \
  --row-height-before 100 --row-height-after 88 >/dev/null 2>"$WORKDIR/err.txt"
code=$?
set -e
[ "$code" -eq 2 ] || fail "expected exit code 2 for a blank name, got $code"
grep -q -- "--name" "$WORKDIR/err.txt" || fail "the error did not name --name"
after=$(cksum "$LOG")
[ "$before" = "$after" ] || fail "the log changed after a rejected add"
echo "refused with exit 2: $(cat "$WORKDIR/err.txt")"

echo
echo "SMOKE OK - add, list and estimate all behave as documented."
