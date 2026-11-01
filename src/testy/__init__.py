"""A small test runner: no collection, no plugins, skips tests whose inputs are unchanged."""

import argparse
import os
import queue
import sys
import threading
from concurrent.futures import Future, ThreadPoolExecutor

from testy import cache, graph, select
from testy.runner import (
    FileResult,
    Outcome,
    format_failure,
    no_breakpoints,
    run_file,
    test_names,
)

__version__ = "0.1.1"


class Colors:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def __call__(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def green(self, text: str) -> str:
        return self("32", text)

    def red(self, text: str) -> str:
        return self("31", text)

    def dim(self, text: str) -> str:
        return self("2", text)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="testy")
    p.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="files, directories or file.py::test_name",
    )
    p.add_argument(
        "-k", help="only tests matching this expression, e.g. 'db and not slow'"
    )
    p.add_argument("-q", "--quiet", action="store_true", help="a dot per test")
    p.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="a line per test (default: a line per file)",
    )
    p.add_argument(
        "-x", "--exitfirst", action="store_true", help="stop after the first failure"
    )
    p.add_argument(
        "--ff",
        "--failed-first",
        action="store_true",
        help="run last run's failures first",
    )
    p.add_argument("--force", action="store_true", help="ignore cached results")
    p.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=os.process_cpu_count(),
        help="threads (default: nproc)",
    )
    p.add_argument(
        "--pdb",
        action="store_true",
        help="debug failures with pdb (runs one file at a time)",
    )
    return p.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # 0: a dot per test (-q), 1: a line per file (default), 2: a line per test (-v).
    level = 0 if args.quiet else min(1 + args.verbose, 2)
    out = sys.stdout
    c = Colors(out.isatty() and "NO_COLOR" not in os.environ)
    # Mirror ruff's default `src = [".", "src"]` so imports resolve the way the graph does.
    sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "src")]

    try:
        selection = select.targets(args.paths)
        match = select.keyword(args.k) if args.k else None
    except select.UsageError as e:
        print(f"testy: {e}", file=sys.stderr)
        return 2

    data = cache.load()
    results = data["results"]
    import_graph = graph.import_graph()
    hasher = graph.Hasher(data["stat"])

    to_run: list[tuple[str, list[str], str, bool]] = []
    cached: list[tuple[str, list[str]]] = []
    # A file ruff didn't see (e.g. gitignored) has unknown deps and no key, so never skip it.
    keys = hasher.keys(
        [p for p in selection if p in import_graph], import_graph, __version__
    )
    for path in sorted(selection):
        key = keys.get(path)
        prev = results.get(path)
        fresh = (
            not args.force and key and prev and prev["key"] == key and prev["passed"]
        )
        want = selection[path]
        partial = want is not None or match is not None
        if fresh and not partial:
            # The key covers the file's contents, so its stored names can't be stale.
            cached.append((path, prev.get("names") or test_names(path)))
            continue
        names = test_names(path)
        if want is not None:
            if missing := sorted(want - set(names)):
                print(f"testy: no test named {path}::{missing[0]}", file=sys.stderr)
                return 2
            names = [n for n in names if n in want]
        if match:
            names = [n for n in names if match(f"{path}::{n}")]
        if not names:
            continue
        if fresh:
            cached.append((path, names))
            continue
        to_run.append((path, names, key, partial))

    if args.ff:
        to_run.sort(key=lambda t: results.get(t[0], {}).get("passed", True))

    # Pad names to the longest so the columns line up (Go's tabs only roughly do).
    files = cached + [(path, names) for path, names, *_ in to_run]
    if level == 2:
        labels = [f"{path}::{n}" for path, names in files for n in names]
    else:
        labels = [path for path, _ in files]
    width = max(map(len, labels), default=0)

    def line(passed: bool, label: str, timing: str) -> str:
        status = c.green("ok  ") if passed else c.red("FAIL")
        return f"{status}  {label:<{width}}  {timing:>8}"

    # Cached tests passed against exactly these inputs, so they're reported as passes.
    dots = False
    for path, names in cached:
        if level == 0:
            out.write(c.green("." * len(names)))
            dots = True
        elif level == 1:
            out.write(line(True, path, "(cached)") + "\n")
        elif level == 2:
            for n in names:
                out.write(line(True, f"{path}::{n}", "(cached)") + "\n")
    out.flush()

    stop = threading.Event()
    finished: list[FileResult] = []
    debugged: set[tuple[str, str]] = set()

    real = sys.stdin, sys.stdout, sys.stderr, sys.breakpointhook

    def debug(path: str, name: str, e: Exception) -> None:
        """Show the failure, then open pdb on it; quitting pdb stops the run."""
        import bdb

        debugged.add((path, name))
        if not isinstance(e, bdb.BdbQuit):  # BdbQuit means `q` at a breakpoint()
            out.write(
                f"\n{c.red('FAIL')} {path}::{name}\n{format_failure(e, c.enabled)}"
            )
            out.flush()
            if not debugger.post_mortem(e, real[0], real[1]):
                return
        stop.set()

    # Tests get no terminal: output from parallel threads would only be noise, and
    # input() or a debugger would wait on a prompt nobody can see. With --pdb only
    # the debugger gets the real terminal, and files run one at a time.
    devnull = open(os.devnull, "r+")  # noqa: SIM115
    sys.stdin = sys.stdout = sys.stderr = devnull
    if args.pdb:
        from testy import debugger

        args.jobs = 1
        hook = debugger.breakpoint_hook(real[0], real[1])
    else:
        hook = no_breakpoints
    if os.environ.get("PYTHONBREAKPOINT") != "0":
        sys.breakpointhook = hook
    # Workers report each test and each finished file here; only this thread prints.
    events: queue.SimpleQueue[tuple[str, Outcome] | Future] = queue.SimpleQueue()
    try:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = {}
            for path, names, key, partial in to_run:
                future = pool.submit(
                    run_file,
                    path,
                    names,
                    stop,
                    args.exitfirst,
                    debug if args.pdb else None,
                    lambda path, outcome: events.put((path, outcome)),
                )
                futures[future] = (key, partial)
                future.add_done_callback(events.put)
            pending = len(futures)
            while pending:
                event = events.get()
                if isinstance(event, tuple):  # a test finished
                    path, o = event
                    if level == 0:
                        out.write(c.green(".") if o.error is None else c.red("F"))
                        dots = True
                    elif level == 2:
                        label = f"{path}::{o.name}"
                        out.write(line(o.error is None, label, f"{o.duration:.3f}s"))
                        out.write("\n")
                    out.flush()
                    continue
                pending -= 1  # a file finished
                result = event.result()
                if not result.outcomes:
                    continue
                finished.append(result)
                key, partial = futures[event]
                # A partial run can't vouch for the tests it skipped, but its failures count.
                if result.complete and (not partial or not result.passed):
                    results[result.path] = {
                        "key": key,
                        "passed": result.passed,
                        "names": [o.name for o in result.outcomes],
                    }
                if level == 1:
                    marks = "".join(
                        c.green(".") if o.error is None else c.red("F")
                        for o in result.outcomes
                    )
                    timing = f"{result.duration:.3f}s"
                    out.write(f"{line(result.passed, result.path, timing)}  {marks}\n")
                    out.flush()
    finally:
        sys.stdin, sys.stdout, sys.stderr, sys.breakpointhook = real
        devnull.close()
        cache.save(data)

    if dots:
        out.write("\n")
    failures = [(r.path, o) for r in finished for o in r.outcomes if o.error]
    for path, o in failures:
        if (path, o.name) in debugged:
            continue  # already shown before its pdb session
        out.write(
            f"\n{c.red('FAIL')} {path}::{o.name}\n{format_failure(o.error, c.enabled)}"
        )

    # Like `go test`: no summary on success, a final FAIL line otherwise.
    if failures:
        out.write(f"\n{c.red('FAIL')}\n")
    out.flush()

    if getattr(sys, "_is_gil_enabled", lambda: True)():
        print(
            "testy: the GIL is enabled, so tests ran one at a time; use a free-threaded Python (e.g. 3.14t)",
            file=sys.stderr,
        )
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except BrokenPipeError:
        # The reader went away (e.g. `testy -vv | head`): stop quietly like other CLIs.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 1
