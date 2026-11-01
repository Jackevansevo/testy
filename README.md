# testy

> [!WARNING]
> testy is a purely experimental project, built to explore a different set of tradeoffs for a Python test runner. It isn't production-ready, isn't published to PyPI, and its behaviour and options may change at any time.

A small, fast Python test runner with a different set of tradeoffs from pytest:

- **Fast.** Test files are found by parsing them, not importing them, so there is no slow collection step.
- **Skips unchanged tests.** Like `go test`, results are cached and a test file only reruns when something it imports has changed.
- **Simple.** No plugins, no `conftest.py`, no fixture injection. Tests are plain functions, and fixtures are plain Python you import.
- **Parallel by default.** On free-threaded Python (3.14t), test files run on real parallel threads.

[![asciicast](https://asciinema.org/a/YEIEfpFVOER3UqUd.png)](https://asciinema.org/a/YEIEfpFVOER3UqUd)

## Installation

testy isn't on PyPI. Install it from GitHub as a development dependency of the project you want to test, so it runs in that project's environment:

```bash
uv add --dev git+https://github.com/Jackevansevo/testy
```

Or with pip:

```bash
pip install git+https://github.com/Jackevansevo/testy
```

For parallel runs, use a free-threaded Python, for example by putting `3.14t` in the project's `.python-version` (`uv python install 3.14t`).

## Usage

```bash
uv run testy                        # run what changed, one line per file
uv run testy -q                     # a dot per test
uv run testy -v                     # a line per test
uv run testy tests/test_todos.py    # files or directories
uv run testy tests/test_todos.py::test_complete
uv run testy -k "todos and not catalog"
uv run testy -x                     # stop after the first failure
uv run testy --ff                   # run last run's failures first
uv run testy --lf                   # run only the tests that failed last time
uv run testy --force                # ignore the cache
uv run testy -j 4                   # threads (default: number of CPUs)
uv run testy --pdb                  # debug failures (one file at a time)
```

Output follows `go test`: no summary when everything passes, and a final `FAIL` line and exit code 1 otherwise.

```
ok    tests/test_arith.py      0.002s  ..
ok    tests/test_stats.py    (cached)
FAIL  tests/test_todos.py      0.206s  ..F..
```

## Writing tests

Tests are top-level functions named `test*` that use plain `assert`. `async def` tests are supported.

There is no fixture system. A fixture is a context manager or function in a module your tests import, so its dependencies show up in the import graph like any other code:

```python
# tests/fixtures/todos.py
import contextlib

from calc.todos import create_app

_app = create_app({"TESTING": True})  # built once, when this module is first imported


@contextlib.contextmanager
def app():
    with _app.app_context():
        yield _app


@contextlib.contextmanager
def client():
    with app() as a:
        yield a.test_client()
```

```python
# tests/test_todos.py
from tests.fixtures.todos import client


def test_create_requires_title():
    with client() as c:
        assert c.post("/todos", json={}).status_code == 400
```

| pytest | testy |
|---|---|
| `scope="function"` fixture | `with fixture():` inside the test |
| `scope="session"` fixture | A module-level value in a fixtures module (Python's import lock builds it once) |
| `conftest.py` | `from tests.fixtures.x import y` |

Split fixtures into modules by topic (`tests/fixtures/numbers.py`, `tests/fixtures/todos.py`). testy tracks dependencies per file, so editing a fixture module reruns only the tests that import it.

### Rules that follow from the design

- **Isolation is your job.** Files run in parallel in one process and share module state, so tests must not modify shared objects or assume a shared database is empty.
- **Test output is discarded.** `print` output never appears. `breakpoint()` and `input()` fail immediately instead of hanging, unless you pass `--pdb`.
- **The cache only sees Python imports within the project.** Use `--force` after changing data files, environment variables or code outside the project.

## Examples

- [`examples/testy`](examples/testy): a Flask and Flask-SQLAlchemy app sharing one in-memory SQLite database across parallel tests (`vfs=memdb`), with testy-style tests.
- [`examples/pytest`](examples/pytest): the same tests written the usual pytest way, with `conftest.py` fixtures as in [Flask's testing docs](https://flask.palletsprojects.com/en/stable/testing/).

```bash
cd examples/testy && uv run testy
cd examples/pytest && uv run pytest
```

## Benchmark

`bench/` generates a synthetic project whose plain-assert tests both runners can run, and times them:

```bash
uv run bench/bench.py --modules 5000 --tests 2000
```

Results on Apple silicon (2 performance and 4 efficiency cores), Python 3.14t, best of 3 runs. Each time includes starting Python. Two suites were used:

- **Fast:** 5,000 modules, 2,000 test files, 20,000 quick tests.
- **CPU-heavy:** 500 modules, 100 test files, 1,000 tests that each do pure-Python work (`--work 200000`).

### Full runs: every test runs

A like-for-like comparison: each runner runs the whole suite, with testy's cache turned off (`--force`). Each pair compares the same mode: one at a time (`pytest` against `testy -j 1`), and in parallel (`pytest -n auto` against `testy`).

| Suite | Mode | pytest | testy | Difference |
|---|---|---|---|---|
| Fast | One at a time | 5.64s | **1.01s** | **−82% (5.6× faster)** |
| Fast | Parallel | 9.42s | **0.90s** | **−90% (10× faster)** |
| CPU-heavy | One at a time | 6.34s | **6.15s** | **−3% (about the same)** |
| CPU-heavy | Parallel | 3.00s | **2.70s** | **−10% (1.1× faster)** |

On the fast suite, 2.20s of pytest's time is collection (`pytest --collect-only`), and most of the rest is pytest's per-test overhead. `pytest -n auto` is slower than plain pytest there, because each worker process collects the whole suite again. On the CPU-heavy suite the tests themselves dominate, so the runners are close.

### Incremental runs: testy's cache

testy only reruns test files whose imports changed. pytest has no equivalent, so after any change it has to run the whole suite again. The pytest column is its fastest full run of each suite from the table above: plain `pytest` for the fast suite, `pytest -n auto` for the CPU-heavy one.

**Fast suite:**

| Scenario | Tests testy runs | testy | pytest | Difference |
|---|---|---|---|---|
| Nothing changed | 0 | **0.31s** | 5.64s | **−95% (18× faster)** |
| Edit a leaf module | 10 | **0.33s** | 5.64s | **−94% (17× faster)** |
| Edit the most-imported module | 20,000 | **0.89s** | 5.64s | **−84% (6.3× faster)** |

**CPU-heavy suite:**

| Scenario | Tests testy runs | testy | pytest | Difference |
|---|---|---|---|---|
| Nothing changed | 0 | **0.09s** | 3.00s | **−97% (33× faster)** |
| Edit a leaf module | 10 | **0.16s** | 3.00s | **−95% (19× faster)** |
| Edit the most-imported module | 1,000 | **2.85s** | 3.00s | **−5% (about the same)** |

Editing the most-imported module reruns every test, so testy does a full run too, and the gap is just the full-run gap.

## Requirements

Python 3.14 or later. Free-threaded Python (`uv python install 3.14t`) is needed for parallel speedups; on a regular build tests still run correctly, one at a time, and testy prints a warning.

## How it works

1. **Discover:** walk the given paths for `test_*.py` and read each file's top-level `test*` functions with `ast`, without importing anything.
2. **Graph:** run `ruff analyze graph` to find which files each file imports, adding the parent `__init__.py` files that importing a module runs.
3. **Hash:** give every file a key built from its own contents plus the keys of everything it imports. Import cycles are grouped and hashed together. The key also covers `uv.lock`, the Python version and testy's version.
4. **Skip:** a file whose key matches its last passing run is reported as `(cached)` and not run.
5. **Run:** the remaining files run in parallel, one file per thread. Each file's tests run in order on that thread.

Results are stored in `.testy/cache.json`.
