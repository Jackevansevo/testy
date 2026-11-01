# testy

> [!WARNING]
> testy is a purely experimental project, built to explore a different set of tradeoffs for a Python test runner. It isn't production-ready, isn't published to PyPI, and its behaviour and options may change at any time.

A small, fast Python test runner with a different set of tradeoffs from pytest:

- **Fast.** Test files are found by parsing them, not importing them, so there is no slow collection step.
- **Skips unchanged tests.** Like `go test`, results are cached and a test file only reruns when something it imports has changed.
- **Simple.** No plugins, no `conftest.py`, no fixture injection. Tests are plain functions, and fixtures are plain Python you import.
- **Parallel by default.** On free-threaded Python (3.14t), test files run on real parallel threads.

<a href="https://asciinema.org/a/YEIEfpFVOER3UqUd"><img src="demo/demo.gif" alt="testy demo" width="886"></a>

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
- **The cache only sees static imports.** See [Cache accuracy](#cache-accuracy).

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

## Cache accuracy

A test file is skipped when its cache key matches its last passing run. The key covers only:

- the contents of the test file and of every project file it imports, directly or indirectly, as reported by `ruff analyze graph` (plus the `__init__.py` files that importing them runs);
- `uv.lock`, if there is one;
- the Python version and testy's version.

Anything else that changes a test's outcome is invisible to the cache, and a stale pass will be reported as `(cached)`:

- **Dynamic imports:** `importlib.import_module`, `__import__`, plugins loaded by entry point, and other imports ruff can't resolve statically.
- **Files a test reads:** anything opened with `open()` or similar, such as JSON fixtures, templates, SQL files and `.env` files.
- **The environment:** environment variables, the clock, randomness, the network, and external services such as databases.
- **Code outside the project:** other repositories, path or editable dependencies, and installed packages when there's no `uv.lock`.
- **Other tests:** state that one test leaves behind for another in the same process.

Run with `--force` after changing any of these, and use `--force` in CI so every test runs there.
