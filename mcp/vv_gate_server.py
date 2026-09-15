#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SwarmLabs verification-gate MCP server — public, HTTP-backed edition.

This is the *distributable* gate server: it has **no dependency on the private
SwarmLabs engine** and answers purely from the published, machine-readable
endpoints on https://swarmlabs.tools. Drop it into any MCP host (Claude Desktop,
Cursor, your own agent runtime) and your research agent can ask, before acting:

    "Is this scenario trustworthy right now — and if not, why?"

Why a public gate matters
-------------------------
Frontier research agents (GPT-6 Astra on the Insilico DDD benchmark, Biomni,
DrugAgent) now generate scientific results with no plugins and no fine-tuning.
Reviews are unanimous that such agents are "prone to plausible-but-wrong outputs,
weak guardrails" and that every deployment needs *a held-out benchmark +
quantified uncertainty + a human checkpoint*. This server is the machine-readable
form of that checkpoint.

What this server can and cannot do (honest boundary)
----------------------------------------------------
- CAN: list the 62 published scenarios, return the verdict summary, return the
  per-scenario gate decision and uncertainty budget, and fetch a full
  10-chapter V&V report.
- CANNOT: run `verify_prediction` on *your own arbitrary predictions*. That
  requires the noise-free ground-truth oracle, which lives in the engine
  (`engine/report_generator.py`) and is not shipped here. It is available via
  the engine-side MCP server in the main repository. We say so explicitly
  instead of returning a confident guess.

Install
-------
    pip install mcp           # the only runtime dependency
    python vv_gate_server.py              # stdio MCP server
    python vv_gate_server.py --selftest   # offline smoke test against the live API

MCP host config
---------------
    { "mcpServers": { "swarmlabs-gate": {
        "command": "python", "args": ["/abs/path/to/vv_gate_server.py"] } } }
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

BASE = "https://swarmlabs.tools"
TIMEOUT = 25

mcp = FastMCP("swarmlabs-gate")


# -----------------------------------------------------------------------------
# HTTP helpers (stdlib only — no engine, no numpy)
# -----------------------------------------------------------------------------
def _get(path: str) -> Any:
    url = BASE + path
    req = urllib.request.Request(url, headers={"User-Agent": "swarmlabs-gate-mcp"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _gate(key: str) -> Optional[dict]:
    try:
        return _get(f"/v3/gate/{key}")
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Tools
# -----------------------------------------------------------------------------
@mcp.tool()
def list_scenarios() -> dict:
    """List all published V&V scenarios (key / domain / verdict) from the live index."""
    idx = _get("/v3/report-index")
    out = [{
        "key": s.get("key"),
        "domain": s.get("domain"),
        "verdict": s.get("verdict"),
        "published": s.get("published"),
    } for s in idx.get("scenarios", [])]
    return {"count": len(out), "scenarios": out}


@mcp.tool()
def get_verdict_summary() -> dict:
    """Published PASS / MARGINAL / REFUTED / ERROR counts (same numbers as the site)."""
    idx = _get("/v3/report-index")
    return {
        "counts": idx.get("counts"),
        "total": idx.get("total"),
        "standard": idx.get("standard"),
        "generated_at_utc": idx.get("generated_at_utc"),
    }


@mcp.tool()
def gate_for_scenario(key: str) -> dict:
    """The trust gate for one scenario.

    Returns gate (PROCEED / PROCEED_WITH_HUMAN_CHECK / BLOCK_AUTONOMOUS_ACTION),
    the verdict, the rationale, and the uncertainty budget. A BLOCK means: do not
    act autonomously on this scenario until a human or more data intervenes.
    """
    g = _gate(key)
    if g is None:
        return {"error": f"no gate entry for {key!r}", "hint": "see list_scenarios()"}
    return g


@mcp.tool()
def get_uncertainty_budget(key: str) -> dict:
    """First-class honesty numbers for a scenario: noise floor, κ, coverage, cal_err, R²."""
    g = _gate(key)
    if g is None:
        return {"error": f"no gate entry for {key!r}"}
    return {"scenario_key": key, "verdict": g.get("verdict"),
            "uncertainty": g.get("uncertainty"), "policy": g.get("policy")}


@mcp.tool()
def get_report(key: str, fmt: str = "json") -> str:
    """Fetch a 10-chapter V&V report for a scenario.

    fmt: "json" (structured report) or "html" (rendered). DOCX is at
    /reports/docx/<key>.docx.
    """
    if fmt == "html":
        return _get(f"/reports/html/{key}.html")
    return json.dumps(_get(f"/v3/report/{key}"), ensure_ascii=False, indent=2)


@mcp.tool()
def verify_prediction(scenario_key: str, predictions: list) -> dict:
    """NOT AVAILABLE in the public edition — stated honestly.

    Verifying a model's *own arbitrary predictions* requires the noise-free
    ground-truth oracle, which lives in the SwarmLabs engine and is not
    distributed here. Use the engine-side MCP server
    (`mcp/swarmlabs_vv_server.py` in the main repository) if you have access.
    """
    return {
        "available": False,
        "reason": "arbitrary-prediction verification needs the noise-free oracle "
                  "(engine-side only); this public server is read-only",
        "alternative": f"GET {BASE}/v3/gate/{scenario_key} for the published gate decision",
    }


# -----------------------------------------------------------------------------
# Self-test
# -----------------------------------------------------------------------------
def _selftest() -> None:
    print("== verdict summary ==", get_verdict_summary().get("counts"))
    ls = list_scenarios()
    print("== scenarios ==", ls["count"])
    if ls["scenarios"]:
        k = ls["scenarios"][0]["key"]
        g = gate_for_scenario(k)
        print("== gate ==", k, g.get("gate"), g.get("verdict"))
        print("== uncertainty ==", get_uncertainty_budget(k).get("uncertainty", {}).get("coverage"))
    print("SELFTEST OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        mcp.run()
