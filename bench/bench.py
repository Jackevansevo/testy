"""Compare testy with pytest and pytest-xdist on a generated project.

    uv run bench/bench.py [--modules 500] [--tests 200] [--work 0] [--repeat 3]

The project is generated in a temp directory outside this repo, so ruff's
.gitignore handling can't hide its files from the import graph.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from gen import generate

TESTY = [sys.executable, "-m", "testy"]
PYTEST = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
# Ignore the caller's PYTEST_ADDOPTS (e.g. `-p no:xdist`) so runs are comparable.
ENV = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}


def run(cmd: list[str], cwd: Path) -> tuple[float, int]:
    """Wall time and number of tests run (passed) for one invocation."""
    start = time.perf_counter()
    proc = subprocess.run(
        cmd, check=False, cwd=cwd, env=ENV, capture_output=True, text=True
    )
    elapsed = time.perf_counter() - start
    if proc.returncode not in (0, 5):  # pytest exits 5 when it collects nothing
        sys.exit(f"{' '.join(cmd)} failed:\n{proc.stdout}{proc.stderr}")
    if cmd[:3] == TESTY[:3]:
        # testy prints a line per file ending in its dots, or "(cached)".
        lines = [ln for ln in proc.stdout.splitlines() if ln and "(cached)" not in ln]
        return elapsed, sum(ln.split()[-1].count(".") for ln in lines)
    m = re.search(r"(\d+) passed", proc.stdout)
    return elapsed, int(m.group(1)) if m else 0


def best(cmd: list[str], cwd: Path, repeat: int, before=None) -> tuple[float, int]:
    results = []
    for n in range(repeat):
        if before:
            before(n)
        results.append(run(cmd, cwd))
    return min(results)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--modules", type=int, default=500)
    p.add_argument("--tests", type=int, default=200, help="test files")
    p.add_argument("--per-file", type=int, default=10)
    p.add_argument("--work", type=int, default=0, help="CPU work per test")
    p.add_argument(
        "--repeat", type=int, default=3, help="runs per scenario; best is reported"
    )
    p.add_argument(
        "--keep", action="store_true", help="don't delete the generated project"
    )
    a = p.parse_args()

    root = Path(tempfile.mkdtemp(prefix="testy-bench-"))
    info = generate(root, a.modules, a.tests, a.per_file, work=a.work)
    print(
        f"{a.modules} modules, {a.tests} test files, {info['tests']} tests, work={a.work}"
    )
    print(
        f"python {sys.version.split()[0]}, GIL {'on' if sys._is_gil_enabled() else 'off'}\n"
    )

    def edit(path: str):
        def before(n: int) -> None:
            with open(root / path, "a") as f:
                f.write(f"# edit {time.time_ns()} {n}\n")

        return before

    rows = [
        ("cold", "pytest", best(PYTEST, root, a.repeat)),
        ("cold", "pytest -n auto", best(PYTEST + ["-n", "auto"], root, a.repeat)),
        ("cold", "testy", best(TESTY + ["--force"], root, a.repeat)),
        (
            "collect only",
            "pytest --collect-only",
            best(PYTEST + ["--collect-only"], root, a.repeat),
        ),
        ("no change", "testy", best(TESTY, root, a.repeat)),
        ("edit leaf module", "testy", best(TESTY, root, a.repeat, edit(info["leaf"]))),
        ("edit hub module", "testy", best(TESTY, root, a.repeat, edit(info["hub"]))),
    ]

    print(f"{'scenario':<18} {'runner':<22} {'time':>8} {'tests run':>10}")
    for scenario, runner, (seconds, ran) in rows:
        print(f"{scenario:<18} {runner:<22} {seconds:>7.2f}s {ran:>10}")

    if a.keep:
        print(f"\nproject kept at {root}")
    else:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
