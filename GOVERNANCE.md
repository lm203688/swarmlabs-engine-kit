# Governance

## Maintainership reality (read this first)

This project has **one maintainer**. That is a fact, not a temporary state — do
not read this repository as having a committee, a foundation, a company, or a
paid team behind it.

| Property | Value |
|---|---|
| Maintainers | **1** |
| Bus factor | **1** |
| Legal entity | **none** |
| Funding | **none (pre-revenue)** |
| Paid support | **no** |

We state this plainly because you are being asked to depend on the output. A
project that hides its bus factor is asking you to discover it later, at the
worst time. See [`SECURITY.md`](SECURITY.md#continuity-plan-what-happens-if-the-maintainer-stops)
for the continuity plan, which is the part that actually matters.

## What this means for you, concretely

**Safe to depend on:**

- The **code** in this repository. MIT-licensed, no dependencies, small
  enough to vendor into your tree. Fork it. Nothing here can be revoked.
- The **artifacts** — gate ledger, anchor file, benchmark sets. They are static
  JSON, published as files. Whatever happens to the hosted service, a copy you
  have already fetched stays readable and re-checkable, and every file is
  digest-anchored (`engine.all_digest`, `oracle_digest`).
- The **method**. The `SKILL.md` and `references/gate-semantics.md` describe
  semantics precisely enough to reimplement.

**Risky to depend on:**

- The **hosted endpoints** (`swarmlabs.tools/v3/*`). One maintainer, no SLA, no
  uptime guarantee, no on-call. They are best-effort.
- **Responsiveness.** Issues may go unanswered. There is no response-time
  commitment and it would be dishonest to imply one.
- Anything requiring a **contract, invoice, DPA, or security questionnaire**.
  There is no entity to sign it.

If your use case cannot tolerate those risks, use the code and the published
artifacts, self-host what you can, and do not build a hard runtime dependency on
the hosted endpoints.

## Decision-making

There is no voting process, because with one maintainer a vote would be
theatre. Decisions are made in public and recorded in the issue or commit that
implements them.

What **is** binding:

1. **The honesty rule.** No claim in this project's output may be stronger than
   the evidence behind it. A PR that makes the output look better without making
   the underlying measurement better will be rejected, even if it's popular.
2. **Fail-closed.** Changes that make a gate more permissive on error — turning
   `BLOCK` into `PROCEED`, inventing a default when policy is missing, or
   reporting "not evaluated" as "passed" — are rejected on principle. See
   `skills/vv-gate/references/gate-semantics.md` §3.
3. **No fabricated numbers.** If a statistic appears in this repository, it must
   be reproducible from the artifacts, with the command to reproduce it stated
   next to it.
4. **Published failures stay published.** Where the two evidence chains disagree
   (see gate-semantics §5), both are reported. Removing the disagreeing chain is
   not an acceptable change.

## Contributions

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Short version: small focused PRs, a
reproduction command for any bug, and no new dependencies in
`skills/vv-gate/` (stdlib only is a hard invariant — it is what makes the gate
runnable inside someone else's harness without a build step).

## Licensing and forks

MIT. There is no CLA and no copyright assignment. Fork freely — a fork is the
most credible continuity guarantee this project can offer, and it is why the
license was not chosen to be more restrictive.

## Continuity plan (what happens if the maintainer stops)

If the hosted service stops, in priority order:

1. **Static artifacts remain.** `reports/gate_ledger.json`,
   `reports/wet_lab_anchors.json`, `reports/benchmark/*` are plain files. Any
   deployment that can serve them keeps the gate usable for `check` and
   `anchors`. Only `verify` needs compute, and it needs nothing but arithmetic.
2. **The verifier is reimplementable.** `/v3/verify` is a pure-arithmetic
   function of (your predictions, the published held-out `y`, the published
   thresholds). Its full specification is in
   `skills/vv-gate/references/gate-semantics.md` §2 and §6.2 — reproduce it in
   about 60 lines of any language.
3. **Notice before shutdown**, in the README and in a release, if the maintainer
   knows in advance.

A fork that keeps serving the static artifacts is strictly better than a
promise. That is the honest answer to bus factor = 1 for a project of this size:
not "more maintainers", but "a failure mode that does not strand your data".
