#!/usr/bin/env bash
# Record demo.sh to demo.cast. Works from any directory.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
asciinema rec --headless --window-size 90x32 --title "testy: skipping unchanged tests" \
    --command "$here/demo.sh" --overwrite --return "$here/demo.cast"
