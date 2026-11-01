"""Generate a synthetic project whose tests both testy and pytest can run.

Source modules form a random import DAG biased towards a few widely imported
"core" modules. Each module's VALUE is computed from the modules it imports,
so the imports are real dependencies, and the generator knows every expected
result ahead of time.

    uv run bench/gen.py OUT [--modules 500] [--tests 200] [--work 0]
"""

import argparse
import random
from pathlib import Path

P = 1_000_003


def module_name(i: int, packages: int) -> tuple[str, str]:
    return f"pkg{i % packages:02d}", f"mod_{i:05d}"


def generate(
    out: Path,
    modules: int = 500,
    tests: int = 200,
    per_file: int = 10,
    fanout: int = 3,
    packages: int = 10,
    work: int = 0,
    seed: int = 0,
) -> dict:
    """Write the project to `out` and return paths useful for benchmarking."""
    rng = random.Random(seed)
    src = out / "src" / "synth"
    for pkg in range(packages):
        (src / f"pkg{pkg:02d}").mkdir(parents=True, exist_ok=True)
        (src / f"pkg{pkg:02d}" / "__init__.py").write_text("")
    (src / "__init__.py").write_text("")
    (out / "tests").mkdir(exist_ok=True)

    (out / "pyproject.toml").write_text(
        '[project]\nname = "synth"\nversion = "0.0.0"\n\n'
        '[tool.pytest.ini_options]\npythonpath = [".", "src"]\ntestpaths = ["tests"]\n'
    )
    (src / "work.py").write_text(
        "def burn(n):\n    total = 0\n    for i in range(n):\n"
        "        total += i * i\n    return total\n"
    )
    (out / "tests" / "fixtures.py").write_text(
        "import contextlib\n\n\n@contextlib.contextmanager\n"
        "def inputs():\n    yield list(range(10))\n"
    )

    values: list[int] = []
    imported_by: list[int] = [0] * modules  # how many modules import each one
    for i in range(modules):
        # Squaring the random number favours low indices, which become hubs.
        deps = sorted({int(i * rng.random() ** 2) for _ in range(fanout)}) if i else []
        for d in deps:
            imported_by[d] += 1
        values.append((sum(values[d] for d in deps) * 31 + i) % P)
        pkg, name = module_name(i, packages)
        lines = [
            f"from synth.{module_name(d, packages)[0]} import {module_name(d, packages)[1]}"
            for d in deps
        ]
        refs = ", ".join(f"{module_name(d, packages)[1]}.VALUE" for d in deps)
        lines += [
            "",
            f"VALUE = (sum([{refs}]) * 31 + {i}) % {P}",
            "",
            "",
            "def f(x):",
            f"    return (x * 31 + VALUE) % {P}",
            "",
        ]
        (src / pkg / f"{name}.py").write_text("\n".join(lines))

    tested_by: list[int] = [0] * modules
    for t in range(tests):
        used = sorted(rng.sample(range(modules), rng.randint(1, 3)))
        use_fixture = rng.random() < 0.3
        lines = [
            f"from synth.{module_name(m, packages)[0]} import {module_name(m, packages)[1]}"
            for m in used
        ]
        if use_fixture:
            lines.append("from tests.fixtures import inputs")
        if work:
            lines.append("from synth.work import burn")
        lines.append("")
        for k in range(per_file):
            m = rng.choice(used)
            tested_by[m] += 1
            mod = module_name(m, packages)[1]
            lines += ["", "", f"def test_{k:03d}():"]
            if work:
                lines.append(f"    burn({work})")
            if use_fixture and k % 2 == 0:
                expected = sum((x * 31 + values[m]) % P for x in range(10))
                lines += [
                    "    with inputs() as xs:",
                    f"        assert sum({mod}.f(x) for x in xs) == {expected}",
                ]
            else:
                lines.append(f"    assert {mod}.f({k}) == {(k * 31 + values[m]) % P}")
        lines.append("")
        (out / "tests" / f"test_{t:05d}.py").write_text("\n".join(lines))

    def path(i: int) -> str:
        pkg, name = module_name(i, packages)
        return f"src/synth/{pkg}/{name}.py"

    leaves = [i for i in range(modules) if imported_by[i] == 0 and tested_by[i]]
    return {
        "hub": path(max(range(modules), key=lambda i: imported_by[i])),
        "leaf": path(min(leaves, key=lambda i: tested_by[i])),
        "tests": tests * per_file,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--modules", type=int, default=500)
    p.add_argument("--tests", type=int, default=200, help="test files")
    p.add_argument("--per-file", type=int, default=10, help="tests per file")
    p.add_argument("--fanout", type=int, default=3, help="max imports per module")
    p.add_argument(
        "--work", type=int, default=0, help="loop iterations of CPU work per test"
    )
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    info = generate(
        a.out, a.modules, a.tests, a.per_file, a.fanout, work=a.work, seed=a.seed
    )
    print(
        f"wrote {a.out}: {a.modules} modules, {a.tests} test files, {info['tests']} tests"
    )


if __name__ == "__main__":
    main()
