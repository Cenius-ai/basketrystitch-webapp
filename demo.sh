#!/usr/bin/env bash
# BasketryStitch end-to-end demo - non-interactive, self-contained, exits 0.
# Everything happens in a throw-away directory, so the demo log shipped in the
# repository is never touched and nothing is left behind.
#
#     sh demo.sh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PYTHON="${PYTHON:-python3}"
TOOL="$SCRIPT_DIR/basketrystitch.py"

WORKDIR=$(mktemp -d)
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

cd "$WORKDIR"
LOG="demo_log.json"

demo() {
  shown=""
  for arg in "$@"; do
    case "$arg" in
      *[[:space:]]*) shown="$shown \"$arg\"" ;;
      *) shown="$shown $arg" ;;
    esac
  done
  printf '\n$ python3 basketrystitch.py%s\n' "$shown"
  "$PYTHON" "$TOOL" "$@"
}

printf 'BasketryStitch demo - a coil-and-stitch pattern log with row shrinkage estimates\n'
printf 'Log for this demo: ./%s (throw-away)\n' "$LOG"

demo --version
demo --log "$LOG" list

echo
echo '--- Recording three finished samples -------------------------------------'
demo --log "$LOG" add --name "Willow Coil" --reed-width 4 --unit in \
  --sample-rows 10 --row-height-before 100 --row-height-after 88
demo --log "$LOG" add --name "Bulrush Tray" --reed-width 10 --unit cm \
  --sample-rows 8 --row-height-before 80 --row-height-after 72
demo --log "$LOG" add --name "Rattan Pouch" --reed-width 3.5 --unit mm \
  --sample-rows 14 --row-height-before 63.5 --row-height-after 55.3

echo
echo '--- The log --------------------------------------------------------------'
demo --log "$LOG" list

echo
echo '--- Projections ----------------------------------------------------------'
demo --log "$LOG" estimate --id 1 --target-rows 50
demo --log "$LOG" estimate --id 1 --target-height 440
demo --log "$LOG" estimate --id 2 --target-rows 24
demo --log "$LOG" estimate --id 3 --target-height 120

echo
echo '--- Errors are one line on stderr, with documented exit codes -------------'
printf '\n$ python3 basketrystitch.py add --name "" ... (expect exit 2)\n'
"$PYTHON" "$TOOL" add --log "$LOG" --name "" --reed-width 4 --sample-rows 10 \
  --row-height-before 100 --row-height-after 88 || echo "(refused, exit $?)"
printf '\n$ python3 basketrystitch.py estimate --id 99 --target-rows 10 (expect exit 2)\n'
"$PYTHON" "$TOOL" estimate --log "$LOG" --id 99 --target-rows 10 || echo "(refused, exit $?)"
printf '\n$ python3 basketrystitch.py estimate --id 1 (expect exit 2)\n'
"$PYTHON" "$TOOL" estimate --log "$LOG" --id 1 || echo "(refused, exit $?)"

printf '\n--- Machine-readable mode ------------------------------------------------\n'
demo --log "$LOG" list --json

printf '\nDemo complete. Your own log lives in ./basketrystitch_log.json - see README.md.\n'
