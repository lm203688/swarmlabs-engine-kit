#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enforce the hard invariant: the gate must run with no build step.

The value of the gate is that a consumer can drop it into their own harness
without installing anything. A third-party import would silently destroy that,
and it would not show up in the live smoke test on a machine that happens to
have the dependency. So it is checked mechanically, in CI, rather than trusted
to review.

Scope: everything under `skills/vv-gate/`, plus the top-level
`vv_gate_server.py` (the stdio MCP server, which is deliberately hand-rolled on
stdlib JSON-RPC instead of taking a dependency on an MCP SDK).

    python skills/vv-gate/tests/check_stdlib_only.py

Exits 1 and prints every offending import if the invariant is broken.
"""

from __future__ import annotations

import ast
import pathlib
import sys

#: Everything these modules are allowed to import. Kept explicit rather than
#: derived from sys.stdlib_module_names, because that attribute only exists on
#: 3.10+ and the floor here is 3.8.
ALLOWED = {
    "__future__",
    "argparse", "ast", "collections", "contextlib", "copy", "dataclasses",
    "datetime", "enum", "functools", "hashlib", "http", "importlib", "io",
    "itertools", "json", "logging", "math", "operator", "os", "pathlib",
    "random", "re", "shlex", "socket", "statistics", "subprocess", "sys",
    "tempfile", "textwrap", "threading", "time", "traceback", "typing",
    "unittest", "urllib",
}

HERE = pathlib.Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]              # skills/vv-gate/
REPO_ROOT = HERE.parents[3]               # repo root


def scope():
    files = sorted(SKILL_ROOT.rglob("*.py"))
    server = REPO_ROOT / "vv_gate_server.py"
    if server.exists():
        files.append(server)
    return files


def main() -> int:
    bad: list[str] = []
    files = scope()
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                # relative imports (level > 0) stay inside the module; fine.
                names = [(node.module or "").split(".")[0]] if node.level == 0 else []
            else:
                continue
            for n in names:
                if n and n not in ALLOWED:
                    bad.append(f"{f.relative_to(REPO_ROOT)}:{node.lineno} imports {n!r}")

    print(f"scanned {len(files)} file(s):")
    for f in files:
        print("  " + str(f.relative_to(REPO_ROOT)))
    for b in bad:
        print("BLOCKED  " + b)
    if bad:
        print(f"\nviolation: the gate must remain stdlib-only "
              f"({len(bad)} third-party import(s)).")
        return 1
    print("ok: stdlib only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
