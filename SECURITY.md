# Security Policy

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Use GitHub's private reporting flow:
<https://github.com/lm203688/swarmlabs-engine-kit/security/advisories/new>

Include: what you did, what happened, what you expected, and the smallest
reproduction you have. If it involves the hosted service
(`swarmlabs.tools/v3/*`), include the `request_id` from the response body — it
is the only handle that ties a response back to a server-side event.

There is **one maintainer** and **no on-call**. You will get an
acknowledgement when a human sees it, not within any promised window. Do not
read a delay as a decision.

## Scope

| In scope | Notes |
|---|---|
| The hosted API (`swarmlabs.tools/v3/*`, `/api/*`) | auth bypass, rate-limit bypass, injection, SSRF, data exposure |
| The gate's correctness as a **security control** | any input that makes `POST /v3/verify` return `PROCEED` when it should return `BLOCK` |
| `skills/vv-gate/scripts/vv_gate.py` | arbitrary code execution, credential leakage |
| The release/CI pipeline | supply-chain issues in what gets published |

**Out of scope:** the scientific accuracy of the models. That is a correctness
and honesty matter, tracked as a normal issue — and where the two evidence
chains disagree it is already published
(`skills/vv-gate/references/gate-semantics.md` §5). A model being wrong about
biology is not a vulnerability; a model being wrong **and reported as PASS at
the gate** is.

## The specific risk we care most about

This service returns an **authorisation decision** — `PROCEED` /
`PROCEED_WITH_HUMAN_CHECK` / `BLOCK_AUTONOMOUS_ACTION`. Any input that downgrades
a decision is a security report by definition:

- submitting a different `x` than the published held-out `x`
- a prediction array of the wrong length, silently padded or truncated
- `y_std` values engineered to inflate coverage
- making `gate_policy` unavailable such that `/v3/verify` falls back to a
  permissive default (it must not — it returns `503`)
- a non-finite value that slips past validation and produces `NaN` in the R²,
  where a `NaN` comparison could read as passing

These are exactly the classes the input validation in
`skills/vv-gate/references/gate-semantics.md` §6.2 is built to refuse, and the
`tests/run_selftest.py` probe has a case for the length check. If you find one
that gets through, that is the most valuable report you can send.

## Secrets

This repository contains no credentials and must not ever contain any. If you
believe a key was exposed:

1. Report privately (link above), and
2. **Rotate it first**, before waiting for a reply. The maintainer cannot
   un-expose it for you.

Client-side: `vv_gate.py` needs no API key to reach `/v3/*` and stores nothing.
If you fork it to add authenticated endpoints, keep credentials in the
environment, never in the file, and never in a `--base`-derived URL.

## Continuity plan (what happens if the maintainer stops)

This section exists in [`GOVERNANCE.md`](GOVERNANCE.md#continuity-plan-what-happens-if-the-maintainer-stops).
The short version, because it matters more than anything else on this page:

- The **code** is MIT and dependency-free — fork it, vendor it, nothing can be
  revoked.
- The **published artifacts** (gate ledger, anchor file, benchmark sets) are
  static JSON with published digests. A copy you already fetched stays
  checkable forever.
- `POST /v3/verify` is pure arithmetic over (your predictions, published `y`,
  published thresholds). It is fully specified in the semantics reference and
  reproducible in ~60 lines of any language.

**Do not build a hard runtime dependency on the hosted endpoints without a
fallback.** That is the honest security posture of a single-maintainer service,
and the mitigation for it is on your side, not ours.

## Supported versions

There are no maintained release branches. `main` is the only supported line.
Pin a commit or a tag if you need stability — tags are immutable, `main` is not.
