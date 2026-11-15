#!/usr/bin/env bash
# BasketryStitch setup: install (nothing to install - standard library only),
# verify the interpreter, then EXIT.  The server/CLI is started separately:
#     python3 basketrystitch.py list
#
#   sh install.sh          # verify the toolchain and the import (offline-safe)
#   sh install.sh --dev    # also install the pinned pytest used by `pytest`
#
# Never uses sudo, never installs system packages, never starts anything.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
DEV=0
case "${1:-}" in
  --dev) DEV=1 ;;
  "") : ;;
  -h | --help)
    echo "usage: sh install.sh [--dev]"
    exit 0
    ;;
  *)
    echo "error: unknown option '$1' (use --dev or nothing)" >&2
    exit 2
    ;;
esac

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: '$PYTHON' not found. BasketryStitch needs Python 3.9 or newer." >&2
  echo "       Install Python 3.9+ and re-run: sh install.sh" >&2
  exit 1
fi

"$PYTHON" - <<'CHECK'
import sys
if sys.version_info < (3, 9):
    sys.exit("error: Python 3.9 or newer is required, found %s" % sys.version.split()[0])
print("python %s ok" % sys.version.split()[0])
CHECK

# No runtime dependencies, but the manifest is still honoured so that a future
# dependency cannot be forgotten.
"$PYTHON" -m pip install --quiet --disable-pip-version-check -r requirements.txt

if [ "$DEV" -eq 1 ]; then
  echo "installing the optional test runner (requirements-dev.txt)"
  "$PYTHON" -m pip install --quiet --upgrade pip setuptools wheel
  "$PYTHON" -m pip install --quiet --disable-pip-version-check -r requirements-dev.txt
fi

# Cheap self-check: a missing import must fail here, not at first run.
"$PYTHON" -c 'import basketrystitch; print("basketrystitch %s ok" % basketrystitch.__version__)'

echo
echo "Setup complete. Nothing to start - this is a command line tool:"
echo "  python3 basketrystitch.py --help"
echo "  python3 basketrystitch.py list"
echo "  sh demo.sh          # recorded end-to-end demo"
echo "  python3 -m unittest discover -s tests"
