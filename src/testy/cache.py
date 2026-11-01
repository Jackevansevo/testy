"""Results of previous runs, stored in .testy/cache.json."""

import json
import os
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
