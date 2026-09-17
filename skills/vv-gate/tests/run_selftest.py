#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live smoke test for skills/vv-gate/scripts/vv_gate.py.

This is a NETWORK test. It talks to the deployed SwarmLabs service, because the
whole point of the skill is that the adjudicator is not local. Run it after any
change to the deployment, or before wiring the gate into a pipeline.

    python tests/run_selftest.py
    SWARMLABS_BASE=https://<preview>.pages.dev python tests/run_selftest.py

Exits 0 on success, 1 on any assertion failure.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, os.pardir, "scripts", "vv_gate.py")
BASE = os.environ.get("SWARMLABS_BASE", "https://swarmlabs.tools").rstrip("/")

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def load_module():
    spec = importlib.util.spec_from_file_location("vv_gate", SCRIPT)
    assert spec and spec.loader, f"cannot load {SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    if not os.path.exists(SCRIPT):
        print(f"vv_gate.py not found at {SCRIPT}")
        return 1
    mod = load_module()

    print(f"base = {BASE}")
    print("[A] transport: explicit UA is set")
    check(bool(mod.USER_AGENT.strip()), f"USER_AGENT = {mod.USER_AGENT!r}")
    check(
        "python-urllib" not in mod.USER_AGENT.lower(),
        "UA is not the stdlib default (Cloudflare 403/1010 otherwise)",
    )

    print("[B] gate -> exit code mapping is fail-closed")
    check(mod.GATE_EXIT.get("PROCEED") == 0, "PROCEED -> 0")
    check(mod.GATE_EXIT.get("BLOCK_AUTONOMOUS_ACTION") == 2, "BLOCK -> 2")
    check(mod.GATE_EXIT.get("PROCEED_WITH_HUMAN_CHECK") == 3, "HUMAN_CHECK -> 3")
    check("ERROR" not in mod.GATE_EXIT, "ERROR has no permissive exit code (must fall through to 1)")

    print("[C] live selftest")
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = mod.main(["--base", BASE, "selftest"])
    except SystemExit as e:  # pragma: no cover
        rc = int(e.code or 0)
    out = buf.getvalue()
    for line in out.rstrip().splitlines():
        print("      | " + line)
    check("SELFTEST OK" in out, "selftest reports OK")
    check(rc == 0, f"selftest exit code = {rc}")

    print("[D] benchmark index exposes a single policy source")
    idx = mod._get(BASE, "/v3/benchmark")
    gp = idx.get("gate_policy") or {}
    check(bool(gp), "gate_policy present (otherwise /v3/verify returns 503)")
    check(gp.get("source") == "engine/verification_gate.py::thresholds()",
          f"policy source = {gp.get('source')!r}")
    check(gp.get("pass_r2") == 0.9, f"pass_r2 = {gp.get('pass_r2')}")
    check(gp.get("z95") == 1.96, f"z95 = {gp.get('z95')}")
    check(idx.get("total", 0) > 0 and idx.get("total_test_points", 0) > 0,
          f"total={idx.get('total')} points={idx.get('total_test_points')}")
    check(bool(idx.get("engine", {}).get("all_digest")), "engine digest published on the index")

    print("[E] ledger is provenance-annotated")
    led = mod._get(BASE, "/v3/gate")
    prov = led.get("provenance") or {}
    eng = prov.get("engine") or {}
    check(bool(eng.get("all_digest")), "ledger carries engine.all_digest")
    check(bool((prov.get("oracle") or {}).get("digest")), "ledger carries oracle.digest")
    check(isinstance(led.get("counts"), dict), f"counts = {led.get('counts')}")

    print("[F] verify refuses a wrong-length submission (fail-closed input check)")
    key = sorted((idx.get("scenarios") or {}).keys())[0]
    st, body = mod._post(BASE, "/v3/verify",
                         {"scenario_key": key, "predictions": [{"x": [0.0], "y_pred": 1.0}]})
    check(st == 400, f"HTTP {st} for a 1-point submission to a multi-point scenario")
    check(body.get("error") == "bad_request", f"error = {body.get('error')!r}")

    print("[G] verify accepts the published oracle (must be PASS at r2 == 1)")
    b = mod._get(BASE, f"/reports/benchmark/{key}.json")
    preds = [{"x": b["X"][i], "y_pred": b["y"][i]} for i in range(len(b["y"]))]
    st, body = mod._post(BASE, "/v3/verify", {"scenario_key": key, "predictions": preds})
    check(st == 200, f"HTTP {st}")
    check(body.get("verdict") == "PASS", f"verdict = {body.get('verdict')}")
    check(body.get("gate") == "PROCEED", f"gate = {body.get('gate')}")
    check(body.get("r2") == 1, f"r2 = {body.get('r2')}")
    check(body.get("x_verified") is True, "x_verified = True")
    check(body.get("coverage") is None, "coverage is null when y_std is omitted (not silently 1)")

    print("[H] anchors: both key spaces resolve")
    anchors = mod._get(BASE, "/v3/anchors")
    lit = (anchors.get("anchors") or [{}])[0].get("key")
    one = mod._get(BASE, f"/v3/anchors/{lit}")
    check(one.get("key") == lit, f"literature anchor {lit} resolves")
    sc_keys = [s.get("scenario_key") for s in (anchors.get("scenarios") or [])]
    check(bool(sc_keys), f"scenario-level dual chains present: {sc_keys[:3]}…")

    print()
    if failures:
        print(f"FAILED ({len(failures)} assertion(s))")
        for f in failures:
            print("  - " + f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
