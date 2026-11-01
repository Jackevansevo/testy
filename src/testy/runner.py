"""Finding test functions and running them."""

import ast
import asyncio
import importlib
import inspect
import io
import os
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {"__pycache__", "node_modules", "venv"}


def discover(args: list[str]) -> list[str]:
    """Paths of test_*.py files under `args`, relative to the cwd.

    Like Go modules, a subdirectory with its own pyproject.toml is a separate
    project and is skipped.
    """
    found = set()
    for arg in args:
        arg = os.path.relpath(arg)
        if os.path.isfile(arg):
            found.add(arg)
            continue
        for dirpath, dirnames, filenames in os.walk(arg):
            dirnames[:] = [
                d
                for d in dirnames
                if not d.startswith(".")
                and d not in SKIP_DIRS
                and not os.path.exists(os.path.join(dirpath, d, "pyproject.toml"))
            ]
            for name in filenames:
                if name.startswith("test_") and name.endswith(".py"):
                    found.add(os.path.normpath(os.path.join(dirpath, name)))
    return sorted(found)


def test_names(path: str) -> list[str]:
    """Top-level test functions in `path`, in source order, without importing it."""
    tree = ast.parse(Path(path).read_bytes(), path)
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test")
    ]


@dataclass
class Outcome:
    name: str
    error: Exception | None
    duration: float = 0.0  # seconds


@dataclass
class FileResult:
    path: str
    outcomes: list[Outcome]
    complete: bool
    duration: float = 0.0  # seconds, import included

    @property
    def passed(self) -> bool:
        return all(o.error is None for o in self.outcomes)


OnFailure = Callable[[str, str, Exception], None]
OnTest = Callable[[str, Outcome], None]


def run_file(
    path: str,
    names: list[str],
    stop: threading.Event,
    failfast: bool,
    on_failure: OnFailure | None = None,
    on_test: OnTest | None = None,
) -> FileResult:
    # perf_counter is monotonic, so wall-clock adjustments can't skew it.
    start = time.perf_counter()
    result = run_tests(path, names, stop, failfast, on_failure, on_test)
    result.duration = time.perf_counter() - start
    return result


def run_tests(
    path: str,
    names: list[str],
    stop: threading.Event,
    failfast: bool,
    on_failure: OnFailure | None,
    on_test: OnTest | None,
) -> FileResult:
    """Run `names` from `path` in order, calling `on_test` as each one finishes."""
    if stop.is_set():
        return FileResult(path, [], complete=False)
    outcomes = []
    module_name = path.removesuffix(".py").replace(os.sep, ".")
    try:
        module = importlib.import_module(module_name)
    except Exception as e:  # noqa: BLE001
        module, error = None, from_test_file(e, path)
        if on_failure:
            on_failure(path, "<import>", error)
    if module is None:
        if failfast:
            stop.set()
        outcome = Outcome("<import>", error)
        if on_test:
            on_test(path, outcome)
        return FileResult(path, [outcome], complete=True)

    for name in names:
        if stop.is_set():
            return FileResult(path, outcomes, complete=False)
        error = None
        start = time.perf_counter()
        try:
            call(getattr(module, name))
        except Exception as e:  # noqa: BLE001
            error = from_test_file(e, path)
            if on_failure:
                on_failure(path, name, error)
        outcome = Outcome(name, error, time.perf_counter() - start)
        outcomes.append(outcome)
        if on_test:
            on_test(path, outcome)
        if error and failfast:
            stop.set()
    return FileResult(path, outcomes, complete=True)


def call(fn) -> None:
    if inspect.iscoroutinefunction(fn):
        asyncio.run(fn())
    else:
        fn()


def no_breakpoints(*args, **kwargs):
    """Stands in for `breakpoint()` while tests run in parallel with no terminal."""
    raise RuntimeError("breakpoint() needs a terminal; rerun with --pdb")


def from_test_file(e: Exception, path: str) -> Exception:
    """`e` with its traceback starting at the test file, and without testy's own
    frames at either end (the runner before it, `no_breakpoints` after it)."""
    tb = e.__traceback__
    test_file = os.path.abspath(path)
    while tb and tb.tb_frame.f_code.co_filename != test_file:
        tb = tb.tb_next
    tb = tb or e.__traceback__
    last = tb
    while last.tb_next:
        if last.tb_next.tb_frame.f_code.co_filename == __file__:
            last.tb_next = None
        else:
            last = last.tb_next
    return e.with_traceback(tb)


def format_failure(e: Exception, color: bool) -> str:
    """A traceback rendered by rich, imported here so passing runs don't pay for it."""
    from rich.console import Console
    from rich.traceback import Traceback

    console = Console(
        file=io.StringIO(),
        force_terminal=color,
        no_color=not color,
        width=shutil.get_terminal_size().columns,
    )
    console.print(Traceback.from_exception(type(e), e, e.__traceback__))
    return console.file.getvalue()
