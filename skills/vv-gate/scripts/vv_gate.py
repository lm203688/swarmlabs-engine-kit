#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vv_gate.py —— SwarmLabs 验证闸门的**零依赖**客户端。

任何 agent / CI / harness 都能用这一支脚本，拿独立第三方对"某个声明是否可信"
的裁决，而不必安装 numpy、不必克隆引擎、不必持 key。

为什么是一个可执行脚本而不是一段提示词
--------------------------------------
验证只有在**能阻断**的时候才算验证。本脚本因此有明确的退出码语义：

    0  gate = PROCEED                    可以继续
    2  gate = BLOCK_AUTONOMOUS_ACTION    禁止自主动作（应作为 CI 硬闸门）
    3  gate = PROCEED_WITH_HUMAN_CHECK   需要人工签字
    1  调用/参数错误

把它放进流水线，`python vv_gate.py check <key>` 返回 2 就会让流水线红掉——
这是"可验证性"落到工程里的样子，而不是文档里的形容词。

覆盖的两个问题不一样，不要混
----------------------------
* ``check`` —— **静态**：这个场景现在的可信状态是什么？（读已发布的门禁账本）
* ``verify`` —— **动态**：**你自己的预测**在这批公开留出点上对不对？（我们持有真值）

瞬时故障会重试，判定失败不会
----------------------------
``429/500/502/503/504`` 与网络错误会退避重试（最多 4 次，尊重 ``Retry-After``）。
``400/404/405`` 一律**立即返回**——它们是对你输入的判定，不是「稍后再试」。
这条区分是刻意的：CI 里一次限流导致的红灯会教人忽略红灯，比不测更糟。

用法
----
    python vv_gate.py scenarios
    python vv_gate.py check microbio_monod
    python vv_gate.py ledger
    python vv_gate.py anchors microbio_monod
    python vv_gate.py template microbio_monod -o preds.json
    python vv_gate.py verify microbio_monod --pred preds.json
    python vv_gate.py selftest

环境
----
    SWARMLABS_BASE   覆盖基址（默认 https://swarmlabs.tools）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = os.environ.get("SWARMLABS_BASE", "https://swarmlabs.tools").rstrip("/")

#: 必须显式设置。Cloudflare 对本站的 Browser-Integrity 规则会拒绝
#: 空 UA 与 stdlib 默认 UA(`Python-urllib/x.y`)，返回 403 + `error code: 1010`。
#: 这是实测结果，不是猜测——见 references/gate-semantics.md 的「消费者注意事项」。
USER_AGENT = "SwarmLabs-VVGate/1.0 (+https://swarmlabs.tools)"

#: 瞬时状态码。**必须与「判定失败」区分开**：CI 里一次限流导致的红灯会教人
#: 忽略红灯，那比不测更糟。这些码重试，其他码（400/404/405/503-policy）立即返回。
TRANSIENT_STATUS = (429, 500, 502, 503, 504)
MAX_ATTEMPTS = 4
BACKOFF_S = (1.5, 4.0, 9.0)

GATE_PROCEED = "PROCEED"
GATE_HUMAN = "PROCEED_WITH_HUMAN_CHECK"
GATE_BLOCK = "BLOCK_AUTONOMOUS_ACTION"
GATE_EXIT = {GATE_PROCEED: 0, GATE_HUMAN: 3, GATE_BLOCK: 2}

_LAST_TRANSPORT = {"retries": 0, "last_status": None}


def _sleep(i: int, retry_after=None) -> None:
    delay = BACKOFF_S[min(i, len(BACKOFF_S) - 1)]
    if retry_after:
        try:
            delay = max(delay, float(retry_after))
        except (TypeError, ValueError):
            pass
    time.sleep(delay)


# ---------------------------------------------------------------- transport
def _get(base: str, path: str, timeout: float = 30.0):
    """GET with retries on transient failures only.

    Returns parsed JSON. Raises HTTPError for non-transient statuses so the
    caller sees the real status (404 means "no such key", not "try again").
    """
    last = None
    for i in range(MAX_ATTEMPTS):
        req = urllib.request.Request(base + path, method="GET",
                                     headers={"User-Agent": USER_AGENT,
                                              "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in TRANSIENT_STATUS:
                raise
            _LAST_TRANSPORT["last_status"] = e.code
            _LAST_TRANSPORT["retries"] = i
            last = e
            if i < MAX_ATTEMPTS - 1:
                _sleep(i, e.headers.get("Retry-After") if e.headers else None)
        except urllib.error.URLError as e:
            _LAST_TRANSPORT["last_status"] = "URLError"
            _LAST_TRANSPORT["retries"] = i
            last = e
            if i < MAX_ATTEMPTS - 1:
                _sleep(i)
    raise last


def _post(base: str, path: str, payload: dict, timeout: float = 90.0):
    """POST. Returns (status, body).

    Retries only on transient statuses and network errors. A 400 is a verdict
    about your input and must be returned immediately - retrying a malformed
    submission would be both pointless and misleading.
    """
    data = json.dumps(payload).encode("utf-8")
    last = None
    for i in range(MAX_ATTEMPTS):
        req = urllib.request.Request(
            base + path, data=data, method="POST",
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json",
                     "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            if e.code not in TRANSIENT_STATUS:
                try:
                    return e.code, json.loads(raw)
                except Exception:
                    return e.code, {"error": "non_json_response", "raw": raw[:400]}
            _LAST_TRANSPORT["last_status"] = e.code
            _LAST_TRANSPORT["retries"] = i
            last = (e.code, raw)
            if i < MAX_ATTEMPTS - 1:
                _sleep(i, e.headers.get("Retry-After") if e.headers else None)
        except urllib.error.URLError as e:
            _LAST_TRANSPORT["last_status"] = "URLError"
            _LAST_TRANSPORT["retries"] = i
            last = e
            if i < MAX_ATTEMPTS - 1:
                _sleep(i)
    if isinstance(last, tuple):
        try:
            return last[0], json.loads(last[1])
        except Exception:
            return last[0], {"error": "non_json_response", "raw": last[1][:400]}
    raise last


# ---------------------------------------------------------------- commands
def cmd_scenarios(args) -> int:
    idx = _get(args.base, "/v3/benchmark")
    counts = idx.get("verdict_counts", {})
    print(f"scenarios: {idx.get('total')}  test points: {idx.get('total_test_points')}  "
          f"standard: {idx.get('standard')}")
    print(f"verdicts : {counts}")
    rows = idx.get("scenarios") or []
    if isinstance(rows, dict):
        rows = [dict(v, key=k) for k, v in rows.items()]
    for r in rows:
        print(f"  {r.get('key') or r.get('scenario_key'):34s} "
              f"verdict={r.get('verdict')}  gate={r.get('gate')}")
    return 0


def cmd_check(args) -> int:
    if args.key:
        e = _get(args.base, f"/v3/gate/{urllib.parse.quote(args.key)}")
        gate = e.get("gate") or e.get("error")
        print(json.dumps(e, ensure_ascii=False, indent=2))
    else:
        led = _get(args.base, "/v3/gate")
        print(f"total={led.get('total')} counts={led.get('counts')}")
        print(f"blocked={led.get('n_blocked')} human_check={led.get('n_human_check_required')}")
        gate = GATE_PROCEED if not led.get("n_blocked") else GATE_BLOCK
    return GATE_EXIT.get(gate, 0)


def cmd_ledger(args) -> int:
    led = _get(args.base, "/v3/gate")
    print(json.dumps({k: v for k, v in led.items() if k != "scenarios"},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_anchors(args) -> int:
    """湿实验锚点（第二证据链）。两个键空间都接受：
    (a) 文献锚点自身（如 ecoli_glucose_Ks）；(b) 场景级双链（如 microbio_monod）。"""
    if args.key:
        one = _get(args.base, f"/v3/anchors/{urllib.parse.quote(args.key)}")
        print(json.dumps(one, ensure_ascii=False, indent=2))
        return 1 if isinstance(one, dict) and one.get("error") else 0
    a = _get(args.base, "/v3/anchors")
    print(json.dumps(a, ensure_ascii=False, indent=2)[:4000])
    return 0


def cmd_template(args) -> int:
    """拉取公开留出集，生成一个可编辑的预测模板（y_pred 留给使用者填）。"""
    b = _get(args.base, f"/reports/benchmark/{urllib.parse.quote(args.key)}.json")
    X, y = b.get("X") or [], b.get("y") or []
    out = {"scenario_key": args.key,
           "predictions": [{"x": X[i], "y_pred": None, "y_std": None}
                           for i in range(len(X))]}
    note = (f"# {len(X)} held-out points (seed {b.get('test_seed')}). "
            "Fill y_pred (and optionally y_std = your 1-sigma). "
            "Keep x unchanged — /v3/verify rejects mis-aligned points.")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(note)
        print(f"wrote {args.out}  (n_points={len(X)}, dim={b.get('dim')}, "
              f"x_oracle_y_len={len(y)})")
    else:
        print(note)
        print(json.dumps(out, ensure_ascii=False, indent=2)[:1200])
    return 0


def cmd_verify(args) -> int:
    if not os.path.exists(args.pred):
        print(f"prediction file not found: {args.pred}", file=sys.stderr)
        return 1
    with open(args.pred, encoding="utf-8") as f:
        payload = json.load(f)
    if "scenario_key" not in payload:
        payload["scenario_key"] = args.key
    preds = payload.get("predictions") or []
    preds = [p for p in preds if p.get("y_pred") is not None]
    if not preds:
        print("no filled predictions found (y_pred is null everywhere). "
              "Run `template` then fill it in.", file=sys.stderr)
        return 1
    payload["predictions"] = preds
    st, body = _post(args.base, "/v3/verify", payload)
    print(json.dumps(body, ensure_ascii=False, indent=2))
    if st != 200:
        return 1
    return GATE_EXIT.get(body.get("gate"), 1)


def cmd_selftest(args) -> int:
    ok = True
    idx = _get(args.base, "/v3/benchmark")
    print(f"[1] benchmark index: total={idx.get('total')} "
          f"points={idx.get('total_test_points')} policy_src="
          f"{(idx.get('gate_policy') or {}).get('source')}")
    if not idx.get("gate_policy"):
        print("    ! gate_policy missing — /v3/verify will refuse (503)"); ok = False
    gp = idx.get("gate_policy") or {}
    print(f"    thresholds: pass_r2={gp.get('pass_r2')} cov_pass={gp.get('coverage_pass')} "
          f"z95={gp.get('z95')} kappa_cap={gp.get('kappa_cap')}")
    led = _get(args.base, "/v3/gate")
    print(f"[2] gate ledger: total={led.get('total')} blocked={led.get('n_blocked')}")
    # verify: feed the published oracle back in -> must PASS at r2 == 1
    key = sorted((idx.get("scenarios") or {}).keys())[0] if isinstance(idx.get("scenarios"), dict) else None
    if key:
        b = _get(args.base, f"/reports/benchmark/{urllib.parse.quote(key)}.json")
        p = [{"x": b["X"][i], "y_pred": b["y"][i]} for i in range(len(b["y"]))]
        st, body = _post(args.base, "/v3/verify", {"scenario_key": key, "predictions": p})
        print(f"[3] verify({key}) self-oracle: HTTP {st} verdict={body.get('verdict')} "
              f"r2={body.get('r2')} gate={body.get('gate')}")
        if st != 200 or body.get("verdict") != "PASS" or body.get("r2") != 1:
            print("    ! expected PASS with r2 == 1"); ok = False
        an = _get(args.base, "/v3/anchors")
        n = len(an.get("anchors") or an.get("scenarios") or an.get("entries") or [])
        print(f"[4] anchors: {n} entries")
    r = _LAST_TRANSPORT["retries"]
    print(f"[5] transport: {r} transient retry(ies), last_status={_LAST_TRANSPORT['last_status']}")
    print("SELFTEST " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


# ---------------------------------------------------------------- cli
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="vv_gate",
        description="SwarmLabs verification gate — independent adjudication, zero deps.")
    ap.add_argument("--base", default=DEFAULT_BASE,
                    help=f"API base (default {DEFAULT_BASE})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scenarios", help="list the 62 published held-out scenarios")
    p.set_defaults(fn=cmd_scenarios)

    p = sub.add_parser("check", help="static gate decision for a scenario")
    p.add_argument("key", nargs="?", help="scenario key; omit for the whole ledger")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("ledger", help="full gate ledger summary (+ provenance)")
    p.set_defaults(fn=cmd_ledger)

    p = sub.add_parser("anchors", help="wet-lab anchors (second evidence chain)")
    p.add_argument("key", nargs="?")
    p.set_defaults(fn=cmd_anchors)

    p = sub.add_parser("template", help="fetch held-out points as an editable prediction file")
    p.add_argument("key")
    p.add_argument("-o", "--out", default=None)
    p.set_defaults(fn=cmd_template)

    p = sub.add_parser("verify", help="verify YOUR predictions on the public held-out set")
    p.add_argument("key")
    p.add_argument("--pred", required=True, help="JSON file {scenario_key, predictions:[...]}")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("selftest", help="live smoke test of the public endpoints")
    p.set_defaults(fn=cmd_selftest)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")[:300]
        print(f"HTTP {e.code}: {raw}", file=sys.stderr)
        if e.code == 403 and "1010" in raw:
            print("hint: Cloudflare rejected this User-Agent. Set an explicit UA "
                  "(empty UA and Python-urllib/... are blocked).", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"network error: {e.reason}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
