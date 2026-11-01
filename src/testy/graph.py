"""Which files each test file depends on, and a hash of their contents."""

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

from ruff.__main__ import find_ruff_bin


def import_graph() -> dict[str, list[str]]:
    """File -> files it imports, for every first-party file under the cwd."""
    out = subprocess.run(
        [find_ruff_bin(), "analyze", "graph", "."],
        capture_output=True,
        text=True,
        check=True,
    )
    graph = json.loads(out.stdout)
    # Importing `a.b.c` also runs `a/__init__.py` and `a/b/__init__.py`, which
    # ruff's graph leaves out, so add them as edges.
    for path, deps in graph.items():
        for parent in Path(path).parents:
            init = str(parent / "__init__.py")
            if init in graph and init != path:
                deps.append(init)
    return graph


def components(roots: list[str], graph: dict[str, list[str]]) -> list[list[str]]:
    """Strongly connected components reachable from `roots` (Tarjan's algorithm).

    Files that import each other in a cycle end up in one component. Components
    come out dependencies-first: each one after everything it imports.
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    out: list[list[str]] = []

    def visit(node: str) -> None:
        index[node] = low[node] = len(index)
        stack.append(node)
        on_stack.add(node)
        work.append((node, iter(graph.get(node, ()))))

    for root in roots:
        if root in index:
            continue
        work: list[tuple[str, Iterator[str]]] = []
        visit(root)
        while work:
            node, children = work[-1]
            for child in children:
                if child not in index:
                    visit(child)
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    component = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == node:
                            break
                    out.append(component)
    return out


class Hasher:
    """Content hashes, skipping files whose mtime and size are unchanged."""

    def __init__(self, stat_cache: dict[str, list]):
        self.stat_cache = stat_cache

    def file(self, path: str) -> str:
        st = os.stat(path)
        entry = self.stat_cache.get(path)
        if entry and entry[0] == st.st_mtime_ns and entry[1] == st.st_size:
            return entry[2]
        digest = hashlib.blake2b(Path(path).read_bytes(), digest_size=16).hexdigest()
        self.stat_cache[path] = [st.st_mtime_ns, st.st_size, digest]
        return digest

    def keys(
        self, roots: list[str], graph: dict[str, list[str]], version: str
    ) -> dict[str, str]:
        """For each file reachable from `roots`, a hash of everything its result
        depends on: its own contents and, recursively, the keys of what it imports.

        Each file is hashed once, so this is linear in the size of the graph
        rather than tests x dependencies.
        """
        salt = hashlib.blake2b(digest_size=16)
        salt.update(version.encode())
        salt.update(sys.version.encode())
        if os.path.exists("uv.lock"):
            salt.update(self.file("uv.lock").encode())

        keys: dict[str, str] = {}
        for component in components(roots, graph):
            members = set(component)
            imported = {
                keys[d] for m in component for d in graph.get(m, ()) if d not in members
            }
            h = salt.copy()
            for m in sorted(component):
                h.update(m.encode())
                h.update(self.file(m).encode())
            for k in sorted(imported):
                h.update(k.encode())
            digest = h.hexdigest()
            for m in component:
                keys[m] = digest
        return keys
