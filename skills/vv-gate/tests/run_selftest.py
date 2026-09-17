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

import http.server
import importlib.util
import io
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout

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


def _is_transient(exc: BaseException) -> bool:
    """True if this exception means 'no verdict was produced', i.e. retryable.

    Groups C–H talk to the deployed service. When it is temporarily
    unreachable, that must **not** be reported as a behavioural regression —
    reporting it as one teaches people to ignore red, which is worse than not
    testing. Exit `4` carries the distinction so CI can retry the step.
    """
    if isinstance(exc, (mod.EdgeBlocked, mod.BadResponse, urllib.error.URLError)):
        return True
    if isinstance(exc, urllib.error.HTTPError) and exc.code in mod.TRANSIENT_STATUS:
        return True
    return False


def _main() -> int:
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
    check(mod.EXIT_UNREACHABLE == 4, f"unreachable -> 4 (got {mod.EXIT_UNREACHABLE})")
    check(2 not in (mod.EXIT_UNREACHABLE,), "unreachable must NOT reuse the BLOCK code 2")

    print("[B2] edge-block classifier is a pure function (no network)")
    ib = mod._is_edge_block
    check(ib(403, '{"error code":1010}') is True, "403 + 1010 -> edge block")
    check(ib(403, "error code: 1010") is True, "403 + 'error code: 1010' -> edge block")
    check(ib(403, "Forbidden") is False, "403 without 1010 -> not an edge block (real verdict)")
    check(ib(404, "1010") is False, "404 carrying '1010' is still a 404, not an edge block")
    check(ib(200, "1010") is False, "a 200 can never be an edge block")
    check(403 not in mod.TRANSIENT_STATUS,
          "403 is not blanket-retried — only the 1010 variant is")
    check(mod.BLOCKED_EDGE_CODE == "1010", f"edge code = {mod.BLOCKED_EDGE_CODE!r}")
    check(mod.MAX_ATTEMPTS >= 2, f"MAX_ATTEMPTS = {mod.MAX_ATTEMPTS} (retry must actually happen)")
    check(429 in mod.TRANSIENT_STATUS and 503 in mod.TRANSIENT_STATUS,
          f"true transient statuses still retried: {mod.TRANSIENT_STATUS}")
    check(400 not in mod.TRANSIENT_STATUS and 404 not in mod.TRANSIENT_STATUS,
          "verdict statuses (400/404) are never retried")

    print("[B3] a 200 with an EMPTY body is retried, then reported as unreachable")
    # CI run #28/#30 failure, reduced to a deterministic test. The runner logged:
    #   GET /reports/benchmark/bio_logistic.json -> json.loads: Expecting value:
    #   line 1 column 1 (char 0)
    # i.e. HTTP 200 with a zero-length body. In the MCP channel the same anomaly
    # surfaced as a bogus 404 unknown_scenario. Both are "no verdict", not "a
    # verdict", and the old client turned the first into an unhandled traceback.

    class FakeEmpty(http.server.BaseHTTPRequestHandler):
        hits = 0

        def do_GET(self):
            type(self).hits += 1
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    saved_sleep = mod._sleep
    mod._sleep = lambda i, retry_after=None: None      # keep the test instant
    srv2 = http.server.HTTPServer(("127.0.0.1", 0), FakeEmpty)
    try:
        threading.Thread(target=srv2.serve_forever, daemon=True).start()
        buf5 = io.StringIO()
        with redirect_stdout(buf5), redirect_stderr(buf5):
            rc_empty = mod.main(["--base", f"http://127.0.0.1:{srv2.server_address[1]}",
                                 "scenarios"])
        out5 = buf5.getvalue()
    finally:
        srv2.shutdown()
        srv2.server_close()
        mod._sleep = saved_sleep
    check(rc_empty == 4, f"empty-body 200 -> exit {rc_empty} (expected 4)")
    check(FakeEmpty.hits == mod.MAX_ATTEMPTS,
          f"retried {FakeEmpty.hits}x (expected {mod.MAX_ATTEMPTS}) — an anomaly, so retry it")
    check("no usable JSON body" in out5 or "empty body" in out5.lower(),
          "stderr names the anomaly instead of a bare JSONDecodeError traceback")
    check("Expecting value" not in out5,
          "no raw JSONDecodeError escapes to the caller")

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
    # Regression guard: the scenario-level endpoint used to 404 on every key,
    # because `scenarios` is a LIST and the worker indexed it with [key].
    if sc_keys:
        sk = sc_keys[0]
        sc = mod._get(BASE, f"/v3/anchors/{urllib.parse.quote(sk)}")
        check(sc.get("scenario_key") == sk, f"scenario anchor {sk} resolves (was 404)")
        check(bool(sc.get("wet_lab")), "scenario anchor carries the wet-lab chain")
        check(bool(sc.get("vv_gate")), "scenario anchor carries the V&V chain (dual display)")

    print("[I] an unreachable adjudicator returns 4 — never 2/3, and never a fake verdict")
    saved_attempts, saved_backoff = mod.MAX_ATTEMPTS, mod.BACKOFF_S
    mod.MAX_ATTEMPTS, mod.BACKOFF_S = 1, (0.0,)  # keep the test instant
    buf2 = io.StringIO()
    try:
        with redirect_stdout(buf2), redirect_stderr(buf2):
            rc_bad = mod.main(["--base", "http://127.0.0.1:59999", "check", "microbio_monod"])
    finally:
        mod.MAX_ATTEMPTS, mod.BACKOFF_S = saved_attempts, saved_backoff
    check(rc_bad == 4, f"exit code = {rc_bad} (expected 4) :: {buf2.getvalue().strip()[:200]}")
    check(rc_bad not in (0, 2, 3),
          "an unreachable gate is never reported as PROCEED / BLOCK / HUMAN_CHECK")
    check("verdict" in buf2.getvalue().lower(),
          "stderr explains that no verdict was produced")

    print("[J] the exact CI failure, reproduced deterministically (local fake edge)")
    # CI run #24: two *live* jobs went red in the same minute while two offline jobs
    # stayed green, on code that had just passed in run #23. Cause: Cloudflare
    # answers 403 + "error code: 1010" non-deterministically. This drives a real
    # socket so the retry loop, the EdgeBlocked type and the exit code are all
    # exercised — a pure-function check would not have caught the original bug.
    class FakeEdge(http.server.BaseHTTPRequestHandler):
        mode = "1010"
        hits = 0

        def _reply(self):
            type(self).hits += 1
            body = (b'<html><head><title>Access denied</title></head><body>'
                    b'<h1>Error 1010</h1>error code: 1010</body></html>'
                    if type(self).mode == "1010"
                    else b'{"error": "Forbidden"}')
            self.send_response(403)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _reply

        def log_message(self, *a):  # silence
            pass

    # MAX_ATTEMPTS stays at its real value so the retry count is meaningful;
    # only the back-off is zeroed so the test does not sleep for 15s.
    mod.BACKOFF_S = (0.0, 0.0, 0.0, 0.0)
    srv = http.server.HTTPServer(("127.0.0.1", 0), FakeEdge)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        FakeEdge.mode, FakeEdge.hits = "1010", 0
        buf3 = io.StringIO()
        with redirect_stdout(buf3), redirect_stderr(buf3):
            rc_edge = mod.main(["--base", f"http://127.0.0.1:{port}", "check", "microbio_monod"])
        out3 = buf3.getvalue()
        check(rc_edge == 4, f"403/1010 -> exit {rc_edge} (expected 4)")
        check(FakeEdge.hits == mod.MAX_ATTEMPTS,
              f"retried {FakeEdge.hits}x (expected {mod.MAX_ATTEMPTS}) — the block is probabilistic")
        check("1010" in out3, "stderr names the actual edge code (not a bare traceback)")
        check("verdict" in out3.lower(), "stderr states that no verdict was produced")

        FakeEdge.mode, FakeEdge.hits = "plain403", 0
        buf4 = io.StringIO()
        with redirect_stdout(buf4), redirect_stderr(buf4):
            rc_403 = mod.main(["--base", f"http://127.0.0.1:{port}", "check", "microbio_monod"])
        check(FakeEdge.hits == 1,
              f"a plain 403 is NOT retried ({FakeEdge.hits} hit(s)) — control case")
        check(rc_403 != 2, f"a plain 403 is not misreported as BLOCK (exit {rc_403})")
    finally:
        srv.shutdown()
        srv.server_close()
        mod.BACKOFF_S = saved_backoff

    print()
    if failures:
        print(f"FAILED ({len(failures)} assertion(s))")
        for f in failures:
            print("  - " + f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


def main() -> int:
    try:
        return _main()
    except Exception as e:                      # noqa: BLE001 - classification is the point
        if not _is_transient(e):
            raise
        print()
        print(f"UNREACHABLE: {type(e).__name__}: {e}")
        print("A live group could not reach the adjudicator, so this run produced no "
              "verdict. Exiting 4 so CI retries the step instead of reporting a "
              "regression that did not happen. Do NOT map this to success.")
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
