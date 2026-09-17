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
- `GOVERNANCE.md` — including an explicit statement of bus factor = 1 and a
  continuity plan describing what remains usable if the hosted service stops.
- `SECURITY.md` — private reporting, scope, the specific class of risk that
  matters here (any input that downgrades a gate decision), and the continuity
  plan restated for the security reader.
- `CONTRIBUTING.md`, `.github/CODEOWNERS`, issue and PR templates,
  `CITATION.cff`.

### Changed

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
