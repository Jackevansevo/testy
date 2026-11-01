#!/usr/bin/env bash
# Record demo.sh to demo.cast, then render demo.gif for the README. Works from any directory.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
asciinema rec --headless --window-size 90x32 --title "testy: skipping unchanged tests" \
    --command "$here/demo.sh" --overwrite --return "$here/demo.cast"
# Rendered at double size; the README shows it at half width, so it stays sharp on
# high-DPI screens.
agg --theme solarized-light --font-size 32 --idle-time-limit 2 --last-frame-duration 5 "$here/demo.cast" "$here/demo.gif"
