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

## Features compared with pytest

| | testy | pytest |
|---|---|---|
| Finding tests | Parses files with `ast`, imports nothing up front | Imports every test module and runs plugin hooks |
| Skipping unchanged tests | Built in, keyed on each file's imports | No (`--lf` reruns last failures only) |
| Parallel runs | Default, threads in one process (free-threaded Python) | `pytest-xdist`, separate worker processes |
| Unit of parallelism | File (tests within a file run in order) | Test (`--dist load`) or file (`--dist loadfile`) |
| Fixtures | Plain imports and context managers | Injected by argument name, `conftest.py`, scopes |
| Selecting tests | Paths, `file.py::test_name`, `-k` expressions | The same, plus markers (`-m`) |
| Output | `go test` style: a line per file, `-q` dots, `-v` a line per test | Dots, `-v`, many plugins |
| Failure details | Tracebacks rendered by rich | Assertion rewriting shows compared values |
| Debugging | `--pdb`, and `breakpoint()` with `--pdb` | `--pdb`, `breakpoint()`, `-s` |
| Stop early / reorder | `-x`, `--ff` | `-x`, `--ff`, `--lf`, and plugins |
| Async tests | `async def` runs with `asyncio.run` | Needs a plugin such as `pytest-asyncio` |
| Configuration | None | `pyproject.toml`, `pytest.ini`, `conftest.py` |
| Plugins | None | Large ecosystem |

### Intentionally not supported

These are left out on purpose, to keep testy small and its caching correct:

- **Fixture injection, `conftest.py` and fixture scopes.** Import what a test needs. Implicit fixtures are invisible to the import graph, so the cache couldn't track them.
- **Plugins and hooks.** There is no extension API.
- **`@pytest.mark.parametrize` and other markers** (`skip`, `xfail`, custom marks). Use a loop, separate functions, or `-k`.
- **Test classes** (`class Test...`, `unittest.TestCase`). Only top-level functions are tests.
- **Assertion rewriting.** Failures show a normal `AssertionError` and traceback. Add a message to the `assert` when you need the values.
- **Showing test output.** `print` output is always discarded, with no `-s`. Output from parallel threads would only be noise.
- **Test isolation.** Files share one process and its module state. Keeping tests independent is the developer's job.
- **Running the tests within one file in parallel.** Split a slow file instead.
- **Tracking data files, environment variables and dynamic imports** (`importlib`, entry points). Run with `--force` after changing them.
- **Tracking code outside the project**, including editable path dependencies. Third-party packages are covered only through `uv.lock`.
- **Configuration files.** All options are command-line flags.
- **Built-in helper fixtures** (`tmp_path`, `monkeypatch`, `capsys`). Use `tempfile`, `unittest.mock` and the like directly.
- **Doctests, coverage integration, reruns of flaky tests and JUnit XML reports.**
- **Python before 3.14.**

## Benchmark

`bench/` generates a synthetic project whose plain-assert tests both runners can run, and times them:

```bash
uv run bench/bench.py --modules 5000 --tests 2000
```

Results on Apple silicon (2 performance and 4 efficiency cores), Python 3.14t, best of 2 runs. Each time includes starting Python.

**5,000 modules, 2,000 test files, 20,000 fast tests:**

| Scenario | Runner | Time | Tests run |
|---|---|---|---|
| Run everything | pytest | 9.27s | 20,000 |
| Run everything | pytest -n auto | 20.35s | 20,000 |
| Run everything | testy `--force` | **1.01s** | 20,000 |
| Collect only | pytest `--collect-only` | 7.77s | 0 |
| Nothing changed | testy | **0.32s** | 0 |
| Edit a leaf module | testy | **0.33s** | 10 |
| Edit the most-imported module | testy | 0.97s | 20,000 |

**100 test files, 1,000 CPU-heavy tests** (`--work 200000`):

| Scenario | Runner | Time | Tests run |
|---|---|---|---|
| Run everything | pytest | 6.62s | 1,000 |
| Run everything | pytest -n auto | 3.63s | 1,000 |
| Run everything | testy `--force` | **3.15s** | 1,000 |
| Nothing changed | testy | **0.08s** | 0 |
| Edit a leaf module | testy | **0.16s** | 10 |

pytest has no equivalent of the cached scenarios: every pytest run collects and runs everything. With fast tests, `pytest -n auto` is slower than plain pytest, because each worker process collects the whole suite again.

## Requirements

Python 3.14 or later. Free-threaded Python (`uv python install 3.14t`) is needed for parallel speedups; on a regular build tests still run correctly, one at a time, and testy prints a warning.
