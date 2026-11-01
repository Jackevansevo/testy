"""Choosing which tests to run: `path::name` targets and `-k` expressions."""

import os
import re
from collections.abc import Callable

from testy.runner import discover


class UsageError(Exception):
    pass


def targets(args: list[str]) -> dict[str, set[str] | None]:
    """Test file -> names asked for with `path::name`, or None for every test in it."""
    selection: dict[str, set[str] | None] = {}
    for arg in args:
        path, _, name = arg.partition("::")
        if not os.path.exists(path):
            raise UsageError(f"no such file or directory: {path}")
        for f in discover([path]):
            want = selection.get(f, set())
            if name and want is not None:
                want.add(name)
                selection[f] = want
            else:
                selection[f] = None
    return selection


TOKEN = re.compile(r"\(|\)|[^\s()]+")


def keyword(expr: str) -> Callable[[str], bool]:
    """A matcher for pytest-style `-k` expressions, e.g. `todo and not catalog`.

    Each word matches case-insensitively as a substring of `path::name`.
    """
    parts = []
    for tok in TOKEN.findall(expr):
        if tok in ("and", "or", "not", "(", ")"):
            parts.append(tok)
        else:
            parts.append(f"({tok.lower()!r} in s)")
    try:
        code = compile(" ".join(parts) or "True", "<-k>", "eval")
    except SyntaxError:
        raise UsageError(f"invalid -k expression: {expr!r}") from None
    # Safe: every word became a string literal, so only and/or/not/in are left.
    return lambda s: bool(eval(code, {"__builtins__": {}}, {"s": s.lower()}))
