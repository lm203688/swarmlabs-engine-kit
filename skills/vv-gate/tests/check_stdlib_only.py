#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enforce the hard invariant: skills/vv-gate/ must run with no build step.

The value of the gate is that a consumer can drop it into their own harness
without installing anything. A third-party import would silently destroy that,
and it would not show up in the live smoke test on a machine that happens to
have the dependency. So it is checked mechanically, in CI, rather than trusted
to review.

    python skills/vv-gate/tests/check_stdlib_only.py

Exits 1 and prints every offending import if the invariant is broken.
"""

from __future__ import annotations

import ast
import pathlib
import sys

#: Everything the gate is allowed to import. Kept explicit rather than derived
#: from sys.stdlib_module_names, because that attribute only exists on 3.10+
#: and the floor for this directory is 3.8.
ALLOWED = {
    "__future__",
    "argparse", "ast", "collections", "contextlib", "copy", "dataclasses",
    "datetime", "enum", "functools", "hashlib", "importlib", "io", "itertools",
    "json", "logging", "math", "operator", "os", "pathlib", "random", "re",
    "shlex", "statistics", "subprocess", "sys", "tempfile", "textwrap", "time",
    "traceback", "typing", "unittest", "urllib",
}

ROOT = pathlib.Path(__file__).resolve().parents[1]   # skills/vv-gate/


def main() -> int:
    bad: list[str] = []
    n_files = 0
    for f in sorted(ROOT.rglob("*.py")):
        n_files += 1
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                # relative imports (level > 0) stay inside the skill; fine.
                names = [(node.module or "").split(".")[0]] if node.level == 0 else []
            else:
                continue
            for n in names:
                if n and n not in ALLOWED:
                    bad.append(f"{f.relative_to(ROOT.parent.parent)}:{node.lineno} imports {n!r}")

    print(f"scanned {n_files} file(s) under {ROOT}")
    for b in bad:
        print("BLOCKED  " + b)
    if bad:
        print(f"\nviolation: skills/vv-gate/ must remain stdlib-only "
              f"({len(bad)} third-party import(s)).")
        return 1
    print("ok: stdlib only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
