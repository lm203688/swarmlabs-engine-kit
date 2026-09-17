# Changelog

All notable changes to this kit. Versions follow the `pyproject.toml` version
field; there are no maintained release branches — `main` is the supported line,
and tags are immutable.

## [0.2.1] — 2026-09-17

### Fixed

- **A Cloudflare `403 error code 1010` could make the gate intermittently
  unavailable on both channels, and there was no way to tell that apart from a
  verdict.** The block is **not deterministic**: CI run `#23` ran four jobs all
  green; run `#24`, with a byte-identical `vv_gate.py` (only docs had changed),
  had its two *live* jobs (`vv-gate-selftest`, `vv-gate-server-selftest`) go red
  in the same minute, while the two *offline* jobs stayed green both times. A
  local loop of the same test passed three times in a row.

  The failure mode mattered more than the flake: a client that cannot reach the
  adjudicator has **no verdict**, yet the old code returned the same `1` it uses
  for "you passed a bad file", and the MCP server returned `gate_unavailable`
  for both a real 404 and an edge block.

  - `scripts/vv_gate.py` now retries `403/1010` alongside `429/5xx` and network
    errors, and on a persistent block raises a distinct `EdgeBlocked` that maps
    to a **new exit code `4` — "unreachable"**, never `2` (BLOCK) and never `0`.
    A plain `403` that does *not* carry `1010` is still returned immediately: it
    is a real rejection, not a coin flip.
  - `vv_gate_server.py` gets the same transport contract and now labels
    unreachability explicitly (`unreachable: true`, `retryable: true`,
    `exit_code: 4`, plus a note) instead of collapsing it into
    `*_unavailable`. No `gate` field is invented, so a model reading the result
    cannot mistake "we never asked" for an implicit pass.
  - `TRANSIENT_STATUS` is deliberately *not* widened to include `403`; the retry
    is keyed on the `1010` body, so a blanket 403 stays fatal.

### Added

- **Deterministic regression tests for the above**, in both channels, because a
  pure-function assertion would not have caught the original bug:
  - `tests/run_selftest.py` group `[J]` stands up a local HTTP server that always
    answers `403 error code: 1010` and asserts the client retried exactly
    `MAX_ATTEMPTS` times and exited `4`; it then flips the fake to a plain `403`
    and asserts a **single** attempt. That second half is the control case —
    without it, "we retry 1010" and "we retry every 403" look identical in logs.
  - `vv_gate_server.py --selftest` runs the same experiment against
    `gate_decision` and additionally checks a dead base
    (`127.0.0.1:59999`) reports `exit_code: 4` with no invented `gate`.
  - `tests/run_selftest.py` group `[I]` asserts an unreachable base exits `4`
    and never `0/2/3`.
  - `tests/check_stdlib_only.py` allow-list gains `http`, `socket`, `threading`
    (all stdlib — the invariant is unchanged); its scope already covered
    `vv_gate_server.py`, which is how this was caught.
- Group `[H]` now guards the scenario-level `/v3/anchors/{scenario_key}`
  regression: that endpoint used to 404 on **every** key because the Worker
  indexed a JSON *array* with a string key. It now asserts both evidence chains
  come back.

### Changed

- `USER_AGENT`-related consumer guidance is now "the block is probabilistic"
  rather than "set a UA and you are fine" — in `SKILL.md` and in
  `references/gate-semantics.md` §6.1/§6.2b, with the CI evidence recorded.
- `vv_gate_server.py` `SERVER_VERSION` → `1.1.0`.

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
