#!/usr/bin/env bash
# A scripted demo of testy, for asciinema. To record it:
#   demo/record.sh   (records this script to demo/demo.cast and demo/demo.gif)
set -euo pipefail
cd "$(dirname "$0")/../examples/testy"
unset PYTHONDONTWRITEBYTECODE  # record what a normal shell would do

# Restore the edited file however the script exits.
edited=src/calc/text.py
backup=$(mktemp)
cp "$edited" "$backup"
trap 'cp "$backup" "$edited"; rm -f "$backup"' EXIT

type_out() {  # print text one character at a time, like someone typing it
    for ((i = 0; i < ${#1}; i++)); do
        printf '%s' "${1:i:1}"
        sleep 0.04
    done
    sleep 0.5
    printf '\n'
}

run() {  # show a prompt, type the command, then run it
    printf '\033[1;32m$\033[0m '
    type_out "$1"
    eval "$1" || true  # some steps fail on purpose
    sleep 2
}

say() {
    printf '\033[2m# %s\033[0m\n' "$1"
    sleep 1.2
}

debug() {  # run `testy --pdb`, typing each pdb command after its prompt
    printf '\033[1;32m$\033[0m '
    type_out "uv run testy --pdb"
    # pdb doesn't echo input that isn't typed at a terminal, so show each command
    # on screen, then send it through a pipe.
    local fifo
    fifo=$(mktemp -u)
    mkfifo "$fifo"
    uv run testy --pdb < "$fifo" &
    local pid=$!
    exec 3> "$fifo"
    sleep 3  # the traceback and the first (Pdb) prompt
    for cmd in "$@"; do
        type_out "$cmd"
        printf '%s\n' "$cmd" >&3
        sleep 2
    done
    exec 3>&-
    wait "$pid" || true
    rm -f "$fifo"
    sleep 2
}

uv run testy --force > /dev/null  # warm up, so the first run shown isn't a cold start

say "Run everything"
run "uv run testy --force"
say "Run again: nothing changed, so every file is cached"
run "uv run testy"
say "Break shout() so it adds two exclamation marks"
run "sed -i '' 's/\"!\"/\"!!\"/' src/calc/text.py"
say "Only the tests that import it rerun, and one fails"
run "uv run testy"
say "Debug the failure"
debug 'p shout("hi")' "c"
say "Fix it and rerun"
run "sed -i '' 's/\"!!\"/\"!\"/' src/calc/text.py"
run "uv run testy"
