# testy

> [!WARNING]
> testy is a purely experimental project, built to explore a different set of tradeoffs for a Python test runner. It isn't production-ready, isn't published to PyPI, and its behaviour and options may change at any time.

A small, fast Python test runner with a different set of tradeoffs from pytest:

- **Fast.** Test files are found by parsing them, not importing them, so there is no slow collection step.
- **Skips unchanged tests.** Like `go test`, results are cached and a test file only reruns when something it imports has changed.
- **Simple.** No plugins, no `conftest.py`, no fixture injection. Tests are plain functions, and fixtures are plain Python you import.
- **Parallel by default.** On free-threaded Python (3.14t), test files run on real parallel threads.

## How it works

1. **Discover:** walk the given paths for `test_*.py` and read each file's top-level `test*` functions with `ast`, without importing anything.
2. **Graph:** run `ruff analyze graph` to find which files each file imports, adding the parent `__init__.py` files that importing a module runs.
3. **Hash:** give every file a key built from its own contents plus the keys of everything it imports. Import cycles are grouped and hashed together. The key also covers `uv.lock`, the Python version and testy's version.
4. **Skip:** a file whose key matches its last passing run is reported as `(cached)` and not run.
5. **Run:** the remaining files run in parallel, one file per thread. Each file's tests run in order on that thread.

Results are stored in `.testy/cache.json`.

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
- **The cache only sees Python imports within the project.** Use `--force` after changing data files, environment variables or code elsewhere (see below).

## Examples

- [`examples/testy`](examples/testy): a Flask and Flask-SQLAlchemy app sharing one in-memory SQLite database across parallel tests (`vfs=memdb`), with testy-style tests.
- [`examples/pytest`](examples/pytest): the same tests written the usual pytest way, with `conftest.py` fixtures as in [Flask's testing docs](https://flask.palletsprojects.com/en/stable/testing/).

```bash
cd examples/testy && uv run testy
cd examples/pytest && uv run pytest
```

## Intentionally not supported

- Fixture injection, `conftest.py` and fixture scopes
- Plugins and hooks
- Parametrize and markers (`skip`, `xfail`)
- Test classes and `unittest.TestCase`
- Assertion rewriting
- Showing test output (`-s`)
- Test isolation
- Parallelism within a file
- Tracking data files, environment variables and dynamic imports
- Tracking code outside the project
- Configuration files
- Built-in helpers (`tmp_path`, `monkeypatch`, `capsys`)
- Doctests, coverage, flaky-test reruns and JUnit XML
- Python before 3.14

## Benchmark

`bench/` generates a synthetic project whose plain-assert tests both runners can run, and times them:

```bash
uv run bench/bench.py --modules 5000 --tests 2000
```

Results on Apple silicon (2 performance and 4 efficiency cores), Python 3.14t, best of 2 runs. Each time includes starting Python. Two suites were used:

- **Fast:** 5,000 modules, 2,000 test files, 20,000 quick tests.
- **CPU-heavy:** 500 modules, 100 test files, 1,000 tests that each do pure-Python work (`--work 200000`).

### Full runs: every test runs

A like-for-like comparison: each runner runs the whole suite, with testy's cache turned off (`--force`).

| Suite | Runner | Time | vs pytest |
|---|---|---|---|
| Fast | pytest | 9.27s | baseline |
| Fast | pytest -n auto | 20.35s | +120% (2.2× slower) |
| Fast | testy `--force` | **1.01s** | **−89% (9.2× faster)** |
| CPU-heavy | pytest | 6.62s | baseline |
| CPU-heavy | pytest -n auto | 3.63s | −45% (1.8× faster) |
| CPU-heavy | testy `--force` | **3.15s** | **−52% (2.1× faster)** |

On the fast suite, 7.77s of pytest's time is collection alone (`pytest --collect-only`). `pytest -n auto` is slower than plain pytest there, because each worker process collects the whole suite again.

### Incremental runs: testy's cache

testy only reruns test files whose imports changed. pytest has no equivalent, so there is nothing to compare against: every pytest run is a full run, as above.

| Scenario | Fast: time | Fast: tests run | CPU-heavy: time | CPU-heavy: tests run |
|---|---|---|---|---|
| Nothing changed | 0.32s | 0 | 0.08s | 0 |
| Edit a leaf module | 0.33s | 10 | 0.16s | 10 |
| Edit the most-imported module | 0.97s | 20,000 | 2.71s | 1,000 |

Editing the most-imported module reruns every test, so it costs about as much as a full run.

## Requirements

Python 3.14 or later. Free-threaded Python (`uv python install 3.14t`) is needed for parallel speedups; on a regular build tests still run correctly, one at a time, and testy prints a warning.
