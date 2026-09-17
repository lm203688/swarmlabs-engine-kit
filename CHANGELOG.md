# Changelog

All notable changes to this kit. Versions follow the `pyproject.toml` version
field; there are no maintained release branches — `main` is the supported line,
and tags are immutable.

## [0.2.0] — 2026-09-17

### Added

- **`skills/vv-gate/`** — a standalone Skill (agentskills.io format) that
  adjudicates a numeric prediction against a published held-out set and returns
  a **blocking** gate. Zero dependencies: Python 3.8+, stdlib only, no API key,
  no numpy, no engine clone.
  - `scripts/vv_gate.py` — `scenarios` / `check` / `ledger` / `anchors` /
    `template` / `verify` / `selftest`, with fail-closed exit codes
    (`0` PROCEED, `3` human check, `2` BLOCK, `1` error).
  - `references/gate-semantics.md` — thresholds, the verdict→gate map, the
    provenance model, measured consumer gotchas, and the published
    disagreements between the two evidence chains.
  - `tests/run_selftest.py` — a live smoke test that asserts the mapping is
    fail-closed, `ERROR` has no permissive exit code, `gate_policy` is
    published, the ledger is provenance-annotated, an unfilled submission is
    refused, and the oracle round-trips to `r2 == 1`.
  - `tests/check_stdlib_only.py` — CI guard for the stdlib-only invariant.
    Mechanical on purpose: a third-party import would not show up in the live
    smoke test on a machine that happens to have the dependency.
- **`vv_gate_server.py`** — a **zero-dependency** MCP stdio server exposing the
  gate as six tools (`list_scenarios`, `gate_decision`, `ledger_provenance`,
  `wet_lab_anchors`, `get_held_out_template`, `verify_prediction`). Hand-rolled
  on stdlib JSON-RPC instead of `pip install mcp` + FastMCP, so it can be
  dropped into an MCP host config and run on a machine with nothing but Python.
  `--selftest` drives a real protocol session against the live service.

  This replaces the previous `mcp/vv_gate_server.py`, which required `pip
  install mcp` **and** documented a boundary ("CANNOT run verify_prediction on
  your own predictions — that requires the noise-free oracle, which is not
  shipped here") that stopped being true when the public `POST /v3/verify`
  endpoint went live. The gate can now actually gate.
- `.github/workflows/ci.yml` — syntax + JSON parse, the stdlib-only invariant,
  and the live smoke test against the deployed service. Unguarded steps: a
  non-zero exit fails the job. The live job going red when the service is down
  is intended — a gate you cannot reach is a gate you do not have.
- `GOVERNANCE.md` — including an explicit statement of bus factor = 1 and a
  continuity plan describing what remains usable if the hosted service stops.
- `SECURITY.md` — private reporting, scope, the specific class of risk that
  matters here (any input that downgrades a gate decision), and the continuity
  plan restated for the security reader.
- `CONTRIBUTING.md`, `CHANGELOG.md`, `CITATION.cff`, `.github/CODEOWNERS`,
  `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/*`. CODEOWNERS
  records the two hard invariants (stdlib-only; fail-closed semantics) next to
  the files they constrain, so review sees them in context.

### Changed

- **`mcp/server.py` → `mcp_server.py` (breaking for anyone importing it).** The
  old documented entry point, `python -m mcp.server`, was wrong: `mcp` is also
  the name of the real Model Context Protocol SDK on PyPI, so that command
  imports **that** package instead of this file and fails with an unrelated
  traceback from `anyio`. Keeping the server at top level as `mcp_server.py`
  removes the collision. Start it with `python mcp_server.py --base-url ...`.
- `mcp_server.py` and `examples/quickstart.py` now run from a fresh clone
  **without** `pip install -e .`, by falling back to the in-repo `src/` layout.
  Previously both died on import, which made "clone and try it" look broken.
- CI additionally asserts that `mcp_server.py --help` works without an install.
- `README.md` — the V&V gate is now the headline capability rather than a
  footnote, with the "reproducible ≠ valid" framing and a consumer warning
  about the Cloudflare `1010` User-Agent behaviour.
- `skills/skill_catalog.json` — registers `vv-gate` as a fifth Skill, with its
  input/output contract, exit-code semantics, and consumer notes.

### Notes

- The published baseline is 62/62 `PASS` with `n_blocked = 0`. A gate that has
  never fired on this baseline is described as such; the `MARGINAL` and
  `REFUTED` paths are exercised by documented negative controls, not by the
  published scenarios.
- The wet-lab anchor chain flags **2 of 10** anchorable scenarios as
  `CONTRADICTED`, including `microbio_monod`, whose fitted `Ks = 0.22 g/L` sits
  44× above the literature ceiling while its V&V chain reports `PASS`. Both
  results are published side by side. That disagreement is the point.

## [0.1.0] — 2026-08-08

### Added

- Initial release: `SwarmLabsClient` SDK, reference MCP server
  (`mcp/server.py`), `skills/skill_catalog.json`, `examples/quickstart.py`,
  `docs/API.md`.
