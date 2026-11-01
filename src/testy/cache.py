"""Results of previous runs, stored in .testy/cache.json."""

import json
import os
from collections.abc import Callable
from pathlib import Path

DIR = Path(".testy")
FILE = DIR / "cache.json"


def load() -> dict:
    try:
        data = json.loads(FILE.read_text())
    except FileNotFoundError, ValueError:
        data = {}
    data.setdefault("stat", {})
    data.setdefault("results", {})
    return data


def save(data: dict) -> None:
    DIR.mkdir(exist_ok=True)
    (DIR / ".gitignore").write_text("*\n")
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
    os.replace(tmp, FILE)


def record(
    prev: dict | None,
    key: str | None,
    ran: list[str],
    failed_now: set[str],
    partial: bool,
    all_names: Callable[[], list[str]],
) -> dict | None:
    """The new entry for a file after a complete run of the tests `ran`, or None to
    keep `prev`.

    An entry lists the tests that failed against `key`, and is `checked` once every
    test in the file has run against it. Only a checked file with no failures has
    `passed`, and only then can it be skipped. Partial runs (`::name`, `-k`, `--lf`)
    carry forward what earlier runs against the same key established.
    """
    if not partial:
        failed, checked = failed_now, True
    elif prev and prev["key"] == key:
        failed = set(prev.get("failed", [])) - set(ran) | failed_now
        checked = prev.get("checked", prev["passed"])
    elif prev and not prev["passed"]:
        # The code changed since those failures: clear the ones that now pass,
        # but the rest of the file still needs a full run against the new key.
        failed = set(prev.get("failed", [])) - set(ran) | failed_now
        checked = False
    elif failed_now:
        failed, checked = failed_now, False
    else:
        return None  # a partial pass says nothing about the tests it didn't run
    passed = checked and not failed
    entry = {"key": key, "passed": passed, "checked": checked, "failed": sorted(failed)}
    if passed:
        entry["names"] = ran if not partial else all_names()
    return entry
