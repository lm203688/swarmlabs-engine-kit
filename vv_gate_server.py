#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SwarmLabs verification-gate MCP server — zero-dependency edition.

Exposes the public SwarmLabs gate as [MCP](https://modelcontextprotocol.io)
tools, so any MCP host (Claude Desktop, Cursor, your own agent runtime) can ask,
*before acting on a number*:

    "Is this claim trustworthy right now - and if not, why?"

Why zero dependencies matters here
----------------------------------
The obvious implementation is `pip install mcp` + FastMCP. We deliberately did
not do that. An MCP server is newline-delimited JSON-RPC 2.0 over stdio - about
a hundred lines. Shipping it with **no install step at all** means it can be
dropped into a host config and just work, on a machine with nothing but Python.
That is the same invariant `skills/vv-gate/` holds, and for the same reason: a
gate you cannot easily run is a gate you do not have.

    python vv_gate_server.py              # stdio MCP server
    python vv_gate_server.py --selftest   # offline-ish smoke test against the live API

MCP host config:

    { "mcpServers": { "swarmlabs-gate": {
        "command": "python",
        "args": ["/abs/path/to/vv_gate_server.py"] } } }

What this server can and cannot do (honest boundary)
---------------------------------------------------
CAN:
  * list the published scenarios and their verdict/gate,
  * return the full gate ledger, with engine/oracle digests,
  * return the wet-lab anchor chain (the second evidence chain), including where
    it CONTRADICTS the V&V chain,
  * hand out the held-out input skeleton for a scenario,
  * **verify your own predictions** against the published held-out set - we hold
    the ground truth, you do not - and return R^2 / coverage / kappa plus a
    fail-closed `PROCEED | PROCEED_WITH_HUMAN_CHECK | BLOCK_AUTONOMOUS_ACTION`.

CANNOT:
  * score an arbitrary grid of your own choosing. Only the published held-out
    set is scored. That is what makes it a gate rather than a benchmarking
    service, and it is a deliberate limit, not a gap.
  * validate the physics. R^2 measures fidelity of a surrogate to its oracle.
    The anchor chain is the chain that can catch an oracle that is physically
    wrong; read both, and gate on the more conservative one.

Transport note: Cloudflare in front of swarmlabs.tools rejects requests with an
empty User-Agent and with the stdlib default `Python-urllib/x.y`
(`403 error code: 1010`). This file always sends an explicit UA, and - because
the block is **not deterministic** - retries it like a transient failure.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SERVER_NAME = "swarmlabs-gate"
SERVER_VERSION = "1.1.0"
PROTOCOL_VERSION = "2024-11-05"
DEFAULT_BASE = os.environ.get("SWARMLABS_BASE", "https://swarmlabs.tools").rstrip("/")
USER_AGENT = f"{SERVER_NAME}/{SERVER_VERSION} (+https://swarmlabs.tools)"

GATE_EXIT = {"PROCEED": 0, "PROCEED_WITH_HUMAN_CHECK": 3, "BLOCK_AUTONOMOUS_ACTION": 2}

#: Same transport contract as `skills/vv-gate/scripts/vv_gate.py`, deliberately
#: duplicated rather than imported: this server must be a single self-contained
#: file that a consumer can drop into an MCP config without a checkout.
#:
#: `403 + error code 1010` is Cloudflare's Browser-Integrity rejection. Measured
#: to be **non-deterministic**: the same explicit UA is served on one attempt and
#: blocked on the next (two live CI jobs went green and red together in the same
#: minute on byte-identical code). So it is retried, and only a persistent block
#: is reported - as *unreachable*, never as a verdict.
TRANSIENT_STATUS = (429, 500, 502, 503, 504)
BLOCKED_EDGE_CODE = "1010"
MAX_ATTEMPTS = 4
BACKOFF_S = (1.5, 4.0, 9.0)
#: Mirrors vv_gate.py: `4` means "no verdict exists", distinct from BLOCK (`2`).
EXIT_UNREACHABLE = 4

_TRANSPORT = {"retries": 0, "edge_blocks": 0, "bad_bodies": 0, "last_status": None}

#: Errors that mean "we never reached the adjudicator", i.e. no verdict exists.
#: `bad_response` is an HTTP 200 with no usable JSON body — measured on CI
#: (2026-09-17) on /reports/benchmark/<key>.json, where it surfaced to the caller
#: as a bogus `unknown_scenario`. A 200-with-nothing is an anomaly, not an answer.
#: The 503 family (`asset_unavailable`, `service_unavailable`, `policy_unavailable`)
#: is the server saying it could not read its own data or thresholds: also no verdict.
UNREACHABLE_ERRORS = ("edge_blocked", "network_error", "bad_response",
                      "asset_unavailable", "service_unavailable", "policy_unavailable")


def _is_edge_block(status, raw) -> bool:
    return status == 403 and BLOCKED_EDGE_CODE in (raw or "")


def _parse_json(raw):
    """(ok, value). An empty or non-JSON body is *not* a value."""
    if not raw or not raw.strip():
        return False, None
    try:
        return True, json.loads(raw)
    except ValueError:
        return False, None


def _sleep(i, retry_after=None):
    delay = BACKOFF_S[min(i, len(BACKOFF_S) - 1)]
    if retry_after:
        try:
            delay = max(delay, float(retry_after))
        except (TypeError, ValueError):
            pass
    time.sleep(delay)


# ------------------------------------------------------------------ transport
def _request(base, path, payload=None, timeout=90.0):
    """Returns (status, body).

    Retries `429/5xx`, network errors and `403/1010` with backoff. `400/404/405`
    come back immediately: they are judgements about the request, and retrying a
    malformed submission would be pointless.

    A persistent edge block returns a structured body rather than raising, since
    an MCP tool result has to be machine-readable for the model that reads it.
    """
    url = base + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    method = "POST" if data else "GET"

    last = None
    saw_edge = False
    bad_body = False
    preview = ""
    for i in range(MAX_ATTEMPTS):
        bad_body = False
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "replace")
                ok, value = _parse_json(raw)
                if ok:
                    return r.status, value
                bad_body = True
                _TRANSPORT["bad_bodies"] += 1
                _TRANSPORT["retries"] = i
                preview = raw[:200]
                if i < MAX_ATTEMPTS - 1:
                    _sleep(i)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            edge = _is_edge_block(e.code, raw)
            if edge:
                _TRANSPORT["edge_blocks"] += 1
                saw_edge = True
            else:
                saw_edge = False
            if e.code not in TRANSIENT_STATUS and not edge:
                try:
                    return e.code, json.loads(raw)
                except Exception:
                    return e.code, {"error": "non_json_response", "raw": raw[:400]}
            _TRANSPORT["last_status"] = e.code
            _TRANSPORT["retries"] = i
            try:
                body = json.loads(raw)
            except Exception:
                body = {"raw": raw[:400]}
            last = (e.code, body)
            if i < MAX_ATTEMPTS - 1:
                _sleep(i, e.headers.get("Retry-After") if e.headers else None)
        except urllib.error.URLError as e:
            _TRANSPORT["last_status"] = "URLError"
            _TRANSPORT["retries"] = i
            saw_edge = False
            last = (0, {"error": "network_error", "reason": str(getattr(e, "reason", e))})
            if i < MAX_ATTEMPTS - 1:
                _sleep(i)
        except (TimeoutError, OSError) as e:
            _TRANSPORT["last_status"] = type(e).__name__
            _TRANSPORT["retries"] = i
            saw_edge = False
            last = (0, {"error": "network_error", "reason": f"{type(e).__name__}: {e}"})
            if i < MAX_ATTEMPTS - 1:
                _sleep(i)

    if bad_body:
        # 注意：必须在解包 `last` 之前返回——一次坏的 2xx 不会写 `last`。
        return 200, {"error": "bad_response", "status": 200, "attempts": MAX_ATTEMPTS,
                     "preview": preview}
    status, body = last
    if saw_edge:
        return status, {
            "error": "edge_blocked",
            "status": status,
            "attempts": MAX_ATTEMPTS,
            "user_agent": USER_AGENT,
            "edge_code": BLOCKED_EDGE_CODE,
        }
    return status, body


def _unavailable(what, st, d):
    """Uniform 'no usable answer' result, with unreachability labelled.

    A tool that returns `gate_unavailable` for both a 404 and a Cloudflare block
    is worse than useless: the model cannot tell "you asked for something that
    does not exist" from "retry in a minute".
    """
    out = {"error": f"{what}_unavailable", "status": st}
    if isinstance(d, dict) and d.get("error") in UNREACHABLE_ERRORS:
        # `cause` 保留底层成因：`edge_blocked`（边缘拦截）与 `bad_response`
        # （200 但无 body）在排障上是两件完全不同的事，不能在这一层被抹平。
        out.update({"unreachable": True, "retryable": True,
                    "cause": d.get("error"),
                    "exit_code": EXIT_UNREACHABLE,
                    "note": ("No verdict was produced: the adjudicator was not reached "
                             f"({d.get('error')}). Cloudflare's 403/1010 block and a 200 "
                             "with an empty body are both non-deterministic upstream "
                             "anomalies. Treat as infrastructure (retry / alert) - never "
                             "as PROCEED (0) and never as BLOCK (2).")})
        if d.get("reason"):
            out["reason"] = d["reason"]
        if d.get("preview"):
            out["preview"] = d["preview"]
    return out


def _maybe_unavailable(what, st, d):
    """Return a labelled failure if this result carries no verdict, else None.

    Keyed on the *error marker*, not on the status code: a `bad_response` is an
    HTTP 200 that contains no answer, so a plain `st != 200` guard would let it
    through and the caller would see a naked `{"error": "bad_response"}` with no
    `exit_code` — exactly the silent path this whole file exists to close.
    """
    if st != 200 or (isinstance(d, dict) and d.get("error") in UNREACHABLE_ERRORS):
        return _unavailable(what, st, d)
    return None


# ---------------------------------------------------------------------- tools
def tool_list_scenarios(base):
    st, idx = _request(base, "/v3/benchmark")
    u = _maybe_unavailable("benchmark", st, idx)
    if u:
        return u
    rows = idx.get("scenarios") or {}
    if isinstance(rows, list):
        rows = {r.get("key") or r.get("scenario_key"): r for r in rows}
    out = [{"scenario_key": k, "verdict": v.get("verdict"), "gate": v.get("gate"),
            "dim": v.get("dim"), "n_test": v.get("n_test")}
           for k, v in sorted(rows.items())]
    return {"total": idx.get("total"), "total_test_points": idx.get("total_test_points"),
            "verdict_counts": idx.get("verdict_counts"), "scenarios": out}


def tool_gate_decision(base, args):
    key = (args or {}).get("scenario_key")
    path = f"/v3/gate/{urllib.parse.quote(key)}" if key else "/v3/gate"
    st, d = _request(base, path)
    u = _maybe_unavailable("gate", st, d)
    if u:
        return u
    d = dict(d) if isinstance(d, dict) else {"body": d}
    d["exit_code"] = GATE_EXIT.get(d.get("gate"), None)
    return d


def tool_ledger_provenance(base):
    st, d = _request(base, "/v3/gate")
    u = _maybe_unavailable("ledger", st, d)
    if u:
        return u
    return {k: d.get(k) for k in
            ("name", "version", "generated_at_utc", "standard", "policy",
             "counts", "total", "n_blocked", "n_human_check_required", "provenance")}


def tool_wet_lab_anchors(base, args):
    key = (args or {}).get("key")
    if key:
        st, d = _request(base, f"/v3/anchors/{urllib.parse.quote(key)}")
        if st == 404:
            return {"error": "unknown_key", "key": key, "status": 404,
                    "hint": "call with no key to list; both literature anchor keys "
                            "(e.g. ecoli_glucose_Ks) and scenario keys "
                            "(e.g. microbio_monod) are accepted"}
        u = _maybe_unavailable("anchors", st, d)
        if u:
            return u
        return d
    st, d = _request(base, "/v3/anchors")
    u = _maybe_unavailable("anchors", st, d)
    if u:
        return u
    return {"summary": d.get("summary"), "anchors": d.get("anchors"),
            "n_scenarios": len(d.get("scenarios") or []), "note": d.get("note")}


def tool_held_out_template(base, args):
    key = (args or {}).get("scenario_key")
    if not key:
        return {"error": "bad_request", "message": "scenario_key is required"}
    st, b = _request(base, f"/reports/benchmark/{urllib.parse.quote(key)}.json")
    if st != 200:
        if isinstance(b, dict) and b.get("error") in UNREACHABLE_ERRORS:
            return _unavailable("template", st, b)
        return {"error": "unknown_scenario", "scenario_key": key, "status": st}
    X = b.get("X") or []
    return {"scenario_key": key, "dim": b.get("dim"), "n_points": len(X),
            "test_seed": b.get("test_seed"),
            "predictions": [{"x": X[i], "y_pred": None, "y_std": None} for i in range(len(X))],
            "note": "Fill y_pred (and optionally y_std = your 1-sigma). Keep x unchanged: "
                    "/v3/verify rejects mis-aligned points with the offending index."}


def tool_verify_prediction(base, args):
    args = args or {}
    key = args.get("scenario_key")
    preds = args.get("predictions")
    if not key:
        return {"error": "bad_request", "message": "scenario_key is required"}
    if not isinstance(preds, list) or not preds:
        return {"error": "bad_request", "message": "predictions must be a non-empty array"}
    preds = [p for p in preds if isinstance(p, dict) and p.get("y_pred") is not None]
    if not preds:
        return {"error": "bad_request",
                "message": "no filled predictions: y_pred is null everywhere. "
                           "Call get_held_out_template first."}
    st, body = _request(base, "/v3/verify", {"scenario_key": key, "predictions": preds})
    if isinstance(body, dict) and body.get("error") in UNREACHABLE_ERRORS:
        # No verdict happened. Say so instead of letting the model read a
        # missing `gate` field as an implicit pass.
        return _unavailable("verify", st, body)
    if not isinstance(body, dict):
        return {"error": "unexpected_response", "status": st, "body": str(body)[:300]}
    out = dict(body)
    out["http_status"] = st
    out["exit_code"] = GATE_EXIT.get(out.get("gate"))
    if st == 400:
        out["note"] = ("fail-closed input check: the submission was refused rather than "
                       "partially scored. Read n_expected/n_got, or index for misalignment.")
    if out.get("coverage") is None:
        out["coverage_note"] = ("coverage is null because y_std was not supplied. "
                               "Null means NOT EVALUATED, which is not the same as 1.")
    return out


TOOLS = [
    {
        "name": "list_scenarios",
        "description": "List the published held-out scenarios with their verdict and gate. "
                       "Call this first to find a scenario_key.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "gate_decision",
        "description": "Static gate decision: what is the current trust state of a scenario? "
                       "Returns gate (PROCEED / PROCEED_WITH_HUMAN_CHECK / "
                       "BLOCK_AUTONOMOUS_ACTION) and exit_code. Omit scenario_key for the "
                       "whole ledger summary.",
        "inputSchema": {"type": "object",
                        "properties": {"scenario_key": {"type": "string"}},
                        "additionalProperties": False},
    },
    {
        "name": "ledger_provenance",
        "description": "Gate ledger summary plus provenance: engine git commit, engine "
                       "all_digest/core_digest and oracle_digest. Use it to check whether "
                       "the gate you are consulting matches the code you think you trust.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "wet_lab_anchors",
        "description": "The second evidence chain: literature ranges (never point estimates) "
                       "and the implied parameters recovered by fitting the noise-free "
                       "oracle. Grades AGREE / NEAR / CONTRADICTED / UNANCHORED. A scenario's "
                       "V&V chain can say PASS while this chain says CONTRADICTED - read both "
                       "and gate on the more conservative one.",
        "inputSchema": {"type": "object",
                        "properties": {"key": {
                            "type": "string",
                            "description": "A literature anchor key (e.g. ecoli_glucose_Ks) or "
                                           "a scenario key (e.g. microbio_monod). Omit to list."}},
                        "additionalProperties": False},
    },
    {
        "name": "get_held_out_template",
        "description": "Fetch a scenario's held-out INPUT points as a fillable skeleton. "
                       "Fill y_pred (optionally y_std = your 1-sigma) and keep x unchanged, "
                       "then call verify_prediction.",
        "inputSchema": {"type": "object",
                        "properties": {"scenario_key": {"type": "string"}},
                        "required": ["scenario_key"], "additionalProperties": False},
    },
    {
        "name": "verify_prediction",
        "description": "THE GATE. Score YOUR predictions on a published held-out set whose "
                       "ground truth we hold. Returns verdict (PASS/MARGINAL/REFUTED/ERROR), "
                       "gate, R^2, coverage (only when y_std is supplied), calibration kappa, "
                       "and exit_code (0 PROCEED / 3 human check / 2 BLOCK). Fail-closed: a "
                       "misaligned or wrong-length submission is refused, not partially "
                       "scored; ERROR maps to BLOCK, never to PROCEED.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario_key": {"type": "string"},
                "predictions": {
                    "type": "array",
                    "description": "One entry per published held-out point, in published order.",
                    "items": {"type": "object", "properties": {
                        "x": {"type": "array", "items": {"type": "number"}},
                        "y_pred": {"type": "number"},
                        "y_std": {"type": "number"}},
                        "required": ["y_pred"]}},
            },
            "required": ["scenario_key", "predictions"],
            "additionalProperties": False,
        },
    },
]

HANDLERS = {
    "list_scenarios": lambda b, a: tool_list_scenarios(b),
    "gate_decision": tool_gate_decision,
    "ledger_provenance": lambda b, a: tool_ledger_provenance(b),
    "wet_lab_anchors": tool_wet_lab_anchors,
    "get_held_out_template": tool_held_out_template,
    "verify_prediction": tool_verify_prediction,
}


# ------------------------------------------------------------------- protocol
def _ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def handle(msg, base):
    """Return a response dict, or None for notifications."""
    method = msg.get("method")
    mid = msg.get("id")
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "initialize":
        return _ok(mid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": ("Independent V&V gate for numeric claims. Reproducible != valid. "
                            "Use verify_prediction to score your own predictions against a "
                            "held-out set whose ground truth this server holds; read "
                            "wet_lab_anchors too, because the two chains are allowed to "
                            "disagree and you must gate on the more conservative one."),
        })
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = HANDLERS.get(name)
        if fn is None:
            return _err(mid, -32602, f"unknown tool: {name}")
        try:
            out = fn(base, args)
        except Exception as e:  # never kill the transport on a tool error
            out = {"error": "tool_exception", "detail": f"{type(e).__name__}: {e}"}
        is_error = isinstance(out, dict) and "error" in out
        return _ok(mid, {
            "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2)}],
            "isError": is_error,
        })
    if mid is None:
        return None
    return _err(mid, -32601, f"method not found: {method}")


def serve(base):
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        resp = handle(msg, base)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def selftest(base):
    """Drive a real protocol session against the live API."""
    ok = True
    #: 无法到达裁决者的检查项。它们**没有结论**，既不算通过也不算回归。
    unreachable = []

    def chk(cond, label):
        nonlocal ok
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            ok = False

    def live(payload, label):
        """标记一次'本应拿到裁决'的调用；若结果为不可达则记录下来。"""
        if isinstance(payload, dict) and payload.get("unreachable"):
            unreachable.append((label, payload.get("error"), payload.get("note")))
            return None
        return payload

    print(f"base = {base}")
    r = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, base)
    chk(r["result"]["serverInfo"]["name"] == SERVER_NAME, "initialize handshake")
    r = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, base)
    names = [t["name"] for t in r["result"]["tools"]]
    chk(len(names) == 6, f"tools/list -> {names}")

    r = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "list_scenarios", "arguments": {}}}, base)
    scen = live(json.loads(r["result"]["content"][0]["text"]), "list_scenarios") or {}
    chk(scen.get("total") == 62, f"list_scenarios total={scen.get('total')}")
    key = (scen.get("scenarios") or [{}])[0].get("scenario_key")
    chk(bool(key), f"first scenario key = {key}")

    r = handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "gate_decision", "arguments": {"scenario_key": key}}}, base)
    gd = live(json.loads(r["result"]["content"][0]["text"]), "gate_decision") or {}
    chk(gd.get("gate") in GATE_EXIT, f"gate_decision gate={gd.get('gate')} exit={gd.get('exit_code')}")

    r = handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                "params": {"name": "ledger_provenance", "arguments": {}}}, base)
    lp = live(json.loads(r["result"]["content"][0]["text"]), "ledger_provenance") or {}
    chk(bool((lp.get("provenance") or {}).get("engine", {}).get("all_digest")),
        "ledger_provenance carries engine.all_digest")

    r = handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                "params": {"name": "wet_lab_anchors",
                           "arguments": {"key": "microbio_monod"}}}, base)
    an = live(json.loads(r["result"]["content"][0]["text"]), "wet_lab_anchors") or {}
    chk(an.get("chains_agree") is False,
        f"dual chain on microbio_monod: vv={((an.get('vv_gate') or {}).get('gate'))} "
        f"wet_lab={((an.get('wet_lab') or {}).get('gate'))} -> disagree")
    chk(((an.get("vv_gate_read") or {}).get("ok")) is not False,
        "the V&V half of the dual chain was actually readable")

    r = handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                "params": {"name": "verify_prediction",
                           "arguments": {"scenario_key": key, "predictions": [{"y_pred": 1.0}]}}}, base)
    vd = live(json.loads(r["result"]["content"][0]["text"]), "verify_prediction") or {}
    chk(vd.get("http_status") == 400, f"wrong-length submission refused (HTTP {vd.get('http_status')})")

    r = handle({"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                "params": {"name": "nope", "arguments": {}}}, base)
    chk("error" in r, "unknown tool -> JSON-RPC error, transport survives")

    # --- unreachability must be distinguishable from a verdict -------------
    chk(_is_edge_block(403, "error code: 1010") is True, "403/1010 classified as an edge block")
    chk(_is_edge_block(403, "Forbidden") is False, "a plain 403 is a real rejection, not an edge block")
    chk(_is_edge_block(404, "1010") is False, "404 is never an edge block")
    chk(EXIT_UNREACHABLE == 4 and EXIT_UNREACHABLE not in (2, 3),
        "unreachable exit code is 4, distinct from BLOCK (2)")
    chk(_parse_json("") == (False, None), "an empty body is not a value")
    chk(_parse_json("   ") == (False, None), "a whitespace-only body is not a value")
    chk(_parse_json("<html>oops</html>")[0] is False, "an HTML body is not JSON")
    chk(_parse_json('{"a":1}') == (True, {"a": 1}), "valid JSON still parses")

    import http.server
    import threading

    class FakeEdge(http.server.BaseHTTPRequestHandler):
        hits = 0
        mode = "1010"

        def _reply(self):
            type(self).hits += 1
            if type(self).mode == "1010":
                body = b"<html><body><h1>Error 1010</h1>error code: 1010</body></html>"
                self.send_response(403)
            else:                                  # HTTP 200, zero-length body
                body = b""
                self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _reply

        def log_message(self, *a):
            pass

    # MAX_ATTEMPTS stays real so the retry count is meaningful; only the
    # back-off is monkeypatched away so the selftest does not sleep ~15s.
    _saved_sleep = globals()["_sleep"]
    globals()["_sleep"] = lambda i, retry_after=None: None
    srv = http.server.HTTPServer(("127.0.0.1", 0), FakeEdge)
    try:
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        FakeEdge.mode, FakeEdge.hits = "1010", 0
        r = handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                    "params": {"name": "gate_decision", "arguments": {}}},
                   f"http://127.0.0.1:{port}")
        edge = json.loads(r["result"]["content"][0]["text"])
        chk(edge.get("unreachable") is True, f"edge block surfaces unreachable=True ({edge.get('error')})")
        chk(edge.get("retryable") is True, "edge block is marked retryable")
        chk(edge.get("exit_code") == EXIT_UNREACHABLE,
            f"edge block carries exit_code={edge.get('exit_code')}")
        chk(edge.get("gate") is None,
            "no gate field is invented on an unreachable result (no implicit pass)")
        chk(FakeEdge.hits == MAX_ATTEMPTS,
            f"retried {FakeEdge.hits}x on 403/1010 (expected {MAX_ATTEMPTS})")

        # The CI run #27 failure, reduced to a deterministic test: HTTP 200 with a
        # zero-length body, which the caller must NOT read as "no such scenario".
        FakeEdge.mode, FakeEdge.hits = "empty", 0
        r = handle({"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                    "params": {"name": "gate_decision", "arguments": {}}},
                   f"http://127.0.0.1:{port}")
        emp = json.loads(r["result"]["content"][0]["text"])
        chk(emp.get("cause") == "bad_response",
            f"empty 200 -> cause={emp.get('cause')!r} (the empty body must survive as the cause)")
        chk(emp.get("unreachable") is True, "an empty 200 is reported as unreachable, not as unknown")
        chk(emp.get("exit_code") == EXIT_UNREACHABLE, "empty 200 carries exit_code=4")
        chk(emp.get("gate") is None, "an empty 200 invents no gate")
        chk(emp.get("error") == "gate_unavailable",
            f"empty 200 surfaces as a *_unavailable, not as a bare transport error ({emp.get('error')})")
        chk(FakeEdge.hits == MAX_ATTEMPTS,
            f"retried {FakeEdge.hits}x on an empty 200 (expected {MAX_ATTEMPTS})")
        chk(_TRANSPORT["bad_bodies"] > 0, f"transport counter bad_bodies={_TRANSPORT['bad_bodies']}")

        r = handle({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                    "params": {"name": "list_scenarios", "arguments": {}}},
                   "http://127.0.0.1:59999")
        dead = json.loads(r["result"]["content"][0]["text"])
        chk(dead.get("unreachable") is True, f"a dead base surfaces unreachable=True ({dead.get('error')})")
        chk(dead.get("exit_code") == EXIT_UNREACHABLE, "a dead base carries exit_code=4, not a verdict")
    finally:
        srv.shutdown()
        srv.server_close()
        globals()["_sleep"] = _saved_sleep

    if unreachable:
        # 无关可达性的检查项仍然会被重跑，所以这里只需把"没有结论"如实说出。
        print()
        print(f"UNREACHABLE: {len(unreachable)} live check(s) produced no verdict:")
        for label, err, _note in unreachable:
            print(f"  - {label}: {err}")
        print("Any FAIL above is a *consequence* of that unreachability, not a "
              "behavioural regression. Exiting 4 so CI retries the step instead of "
              "reporting a regression that did not happen. Do NOT map this to success.")
        return 4

    print("SELFTEST " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    base = DEFAULT_BASE
    if "--base" in argv:
        base = argv[argv.index("--base") + 1].rstrip("/")
    if "--selftest" in argv:
        return selftest(base)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    serve(base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
