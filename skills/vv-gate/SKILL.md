---
name: vv-gate
description: Use when an agent, harness, or CI pipeline produces a scientific/numeric prediction and you need an INDEPENDENT third-party adjudication of whether that claim is trustworthy before acting on it. Also use when you need to turn "the agent said it validated itself" into a blocking gate with a real exit code. Covers static gate lookup for 62 published held-out scenarios, dynamic verification of YOUR OWN predictions against a held-out set the vendor holds the ground truth for, and the wet-lab anchor cross-check.
license: MIT
allowed-tools: Bash
metadata:
  version: "1.0.0"
  author: SwarmLabs
  homepage: https://swarmlabs.tools
  spec: agentskills.io
---

# V&V Gate — independent adjudication for numeric claims

Most "verification" in agent pipelines is the agent grading its own homework.
This skill is a **read-only client to a gate you do not control**, so the answer
can actually be "no".

> **Core distinction, and the reason this skill exists at all:**
> *reproducible ≠ valid*. A fully reproducible experiment can be fully wrong.
> SwarmLabs does not sell reproducibility (git already does that). It sells
> **adjudication against held-out ground truth plus literature anchors.**

## Two different questions — do not mix them

| Question | Command | Where the truth lives |
|---|---|---|
| *What is the current trust state of scenario X?* | `check X` | vendor's published gate ledger (static) |
| *Are **my** predictions on this held-out set correct?* | `verify X --pred p.json` | held-out set whose **y the vendor holds**, you don't |

`check` answers "is this scenario's surrogate trustworthy at all".
`verify` answers "**you** are wrong". Only the second one is a gate on your agent.

## Prerequisite

Zero dependencies. Python 3.8+ stdlib only. No API key, no numpy, no engine
clone. The script is self-contained:

```bash
python skills/vv-gate/scripts/vv_gate.py selftest
```

`selftest` is a **live** smoke test (it hits the public endpoints, it is not a
unit test). Expected shape:

```
[1] benchmark index: total=62 points=3110 policy_src=engine/verification_gate.py::thresholds()
[2] gate ledger: total=62 blocked=0
[3] verify(<first-key>) self-oracle: HTTP 200 verdict=PASS r2=1 gate=PROCEED
[4] anchors: 6 entries
SELFTEST OK
```

If it prints `SELFTEST FAILED`, stop and read `references/gate-semantics.md`
before wiring it into anything.

## Exit codes are the product

Verification that cannot block is not verification, so the exit code is the
contract:

| Code | gate | Meaning |
|---|---|---|
| `0` | `PROCEED` | claim cleared |
| `3` | `PROCEED_WITH_HUMAN_CHECK` | needs a human signature |
| `2` | `BLOCK_AUTONOMOUS_ACTION` | **must halt the autonomous action** |
| `4` | — | **unreachable** — edge block / network failure; *no verdict exists* |
| `1` | — | local call/parameter error (bad JSON, unfilled template, non-JSON reply) |

`2` and `4` are deliberately separate. A gate you cannot reach is not a gate —
but if "cannot reach" and "ruled against you" share an exit code, an operator
cannot tell "fix the network" from "stop the work". Alert and retry on `4`;
halt on `2`.

## Wire it in as a hard gate

```bash
# CI: block the merge if the model's claim does not survive held-out truth
python skills/vv-gate/scripts/vv_gate.py template microbio_monod -o preds.json
# ... your harness fills preds.json: y_pred (and optionally y_std = your 1-sigma)
python skills/vv-gate/scripts/vv_gate.py verify microbio_monod --pred preds.json
# exit 2 -> pipeline red. exit 3 -> requires review.
# exit 0 -> proceed. exit 4 -> infrastructure: retry, do not read as a verdict.
```

GitHub Actions:

```yaml
- name: V&V gate
  run: |
    python skills/vv-gate/scripts/vv_gate.py \
      verify "$SCENARIO" --pred preds.json
```

Leave the step **unguarded** — a non-zero exit fails the job. Do not append
`|| true`.

If `4` becomes noisy in your environment, do **not** swallow it. Retry the step
or alert on it separately; converting it to success would mean your pipeline
silently proceeds when nobody adjudicated anything.

## Commands

```bash
python vv_gate.py scenarios                          # 62 scenarios + verdicts
python vv_gate.py check                              # whole ledger + counts
python vv_gate.py check microbio_monod               # one scenario's gate
python vv_gate.py ledger                             # ledger + provenance (commit/digests)
python vv_gate.py anchors                            # wet-lab anchor list
python vv_gate.py anchors ecoli_glucose_Ks           # one anchor, with source ranges
python vv_gate.py anchors microbio_monod             # scenario-level dual chain
python vv_gate.py template microbio_monod -o p.json  # editable prediction file
python vv_gate.py verify microbio_monod --pred p.json
python vv_gate.py selftest
```

`--base <url>` or `SWARMLABS_BASE` overrides the target. Use it to pin a
deployment instead of tracking `main`.

## Consumer gotchas (all measured, not guessed)

1. **Cloudflare will 403 you if you send no User-Agent, or send the stdlib
   default `Python-urllib/3.x`.** The response body is `error code: 1010`.
   Empty UA and `Python-urllib` are **blocked**; `curl`, `python-requests`,
   `node-fetch`, `axios`, `Go-http-client`, `okhttp` and any explicit custom UA
   are **allowed**. If you re-implement the client, set a UA. `vv_gate.py`
   already sends `SwarmLabs-VVGate/1.0 (+https://swarmlabs.tools)`.
   **The block is not deterministic** — the same explicit UA is served on one
   attempt and 403'd on the next. Measured on GitHub Actions: two live jobs in
   the same minute, running byte-identical code, went green and red together
   while both offline jobs stayed green. So a single 1010 must never be read as
   "the service is broken". `vv_gate.py` retries it like a transient failure and
   only then reports exit `4`.
2. **`x` must be byte-identical to the published held-out `x`.** Any point
   whose `x` differs by more than `1e-6` is rejected with `400` and the offending
   `index`. Do not resample, reorder, or normalise. Use `template` as the base.
3. **`y_std` is optional but changes what you get.** Without it you get `r2`
   and `verdict`; with it you additionally get `coverage`, `calibration_kappa`
   and the over-confidence flag. A model can pass on `r2` and still be
   `agent_overconfident`.
4. **Prediction count must equal the published count.** Wrong length returns
   `400 bad_request` with `n_expected` / `n_got`, not a partial score.
5. **Thresholds are not in this repo and not in your client.** They are
   exported at build time from `engine/verification_gate.py::thresholds()` into
   the published `gate_policy`. `policy_source` in every `/v3/verify` response
   tells you where they came from. There is exactly one copy of the numbers.
6. **The ledger carries provenance.** `engine.git_commit`, `engine.all_digest`,
   `oracle_digest` let you tell whether the gate you just consulted matches the
   code you think you're trusting.
7. **A 2xx is not automatically an answer.** `/reports/benchmark/<key>.json` was
   measured answering `200` with a **zero-length body**; `json.loads` then raises
   `Expecting value: line 1 column 1`, which looks like a bug in your client and
   is not. Parse every response and treat "nothing to parse" as a transport
   anomaly worth retrying. `vv_gate.py` does this and then exits `4`.
8. **`503 asset_unavailable` means "we could not read our own data" — it is not
   a bad scenario key.** Do not translate it into "unknown scenario" in your own
   client. It carries `retryable: true`; `404 unknown_scenario` is the only
   response that means the key does not exist.

Never send a `x` that you modified "to make it fit". A mis-aligned submission
is rejected rather than silently scored — that is deliberate.

## What this skill does NOT do

State these honestly when you present results:

- It does **not** validate the physics. It validates a prediction against a
  held-out surrogate/oracle, and cross-checks against literature ranges. If the
  oracle itself is wrong, `PASS` means "faithful to the oracle", nothing more.
  The second evidence chain (wet-lab anchors) exists precisely to catch that,
  and it **does** report `CONTRADICTED` / `UNANCHORED` for real scenarios.
- It does **not** cover all 62 scenarios in the anchor chain — most have no
  physical counterpart to anchor against, and those are reported as absent, not
  as passing.
- It does **not** let you submit an arbitrary grid. Only the published held-out
  set is scored. That is why it is a gate rather than a benchmarking service.
- **The current baseline has `n_blocked = 0`.** Do not quote a non-zero block
  count as evidence that the gate works. The gate is *fail-closed* — `REFUTED`
  and `ERROR` both map to `BLOCK_AUTONOMOUS_ACTION` — but on the 2026-09-15
  baseline all 62 scenarios pass. A block count of 0 is the honest number, and
  a gate that has never fired is a gate whose teeth you have not yet seen.

## Files

| Path | What |
|---|---|
| `scripts/vv_gate.py` | the client (stdlib only, single file) |
| `references/gate-semantics.md` | thresholds, verdict→gate mapping, provenance, UA probe results |
| `tests/run_selftest.py` | live smoke test: exit-code mapping, fail-closed semantics, provenance, dual chains, unreachability — plus a local fake edge that reproduces the non-deterministic `1010` |
| `tests/check_stdlib_only.py` | CI guard for the stdlib-only invariant |
