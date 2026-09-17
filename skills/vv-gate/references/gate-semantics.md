# Gate semantics — what the V&V gate does and does not assert

Everything in this file is **measured against the deployed service**, not
inferred from the source. Where a number could drift, the file says how to
re-measure it instead of asserting it.

## 1. Why adjudication is not reproducibility

The distinction this whole skill rests on:

> **可复现 ≠ 有效。一个完全可复现的实验可以完全错误。**
> *Reproducible ≠ valid. A fully reproducible experiment can be fully wrong.*

Reproducibility is a property of provenance (git branches, container digests,
seeds). It says the same wrong thing twice. The gate asserts something
different and weaker in a specific way: **that a prediction survives comparison
against held-out ground truth, and survives a cross-check against independent
literature ranges.** Those are two independent chains, and a claim needs both.

| | Reproducible artifact | This gate |
|---|---|---|
| Output | commit / digest you can re-run | verdict + gate on a claim |
| Wrong-but-reproducible | passes | caught, if the held-out truth disagrees |
| Oracle itself wrong | invisible | caught by the **anchor chain**, not the R² chain |
| Failure mode when it fails | you cannot re-run it | it blocks your autonomous action |
| What it optimises | "same result again" | "**should this have been blocked?**" |

The KPI of a gate is what it **stops**, not what it computes.

## 2. Thresholds — exactly one copy

The client does not hold thresholds, and neither does this repo. They are
exported at build time from `engine/verification_gate.py::thresholds()` into the
published `gate_policy`, and the Worker reads them from there at request time.
Every `/v3/verify` response echoes `policy_source`.

Current published values (`GET /v3/benchmark` → `gate_policy`):

| Field | Value | Meaning |
|---|---|---|
| `pass_r2` | `0.9` | out-of-sample R² needed for `PASS` |
| `marginal_r2` | `0.7` | floor for `MARGINAL` |
| `coverage_pass` | `0.9` | one-sided lower bound on empirical coverage for `PASS` |
| `coverage_marginal` | `0.8` | floor for `MARGINAL` |
| `noise_floor` | `0.03` | 3% noise floor — deliberately **not** driven to zero |
| `nominal_coverage` | `0.95` | the nominal 95% band `z95` corresponds to |
| `kappa_cap` | `40.0` | cap on the calibration-inflation suggestion κ |
| `z95` | `1.96` | must match `report_generator.py`; the Worker has no numpy |
| `source` | `engine/verification_gate.py::thresholds()` | provenance of the numbers |

If `gate_policy` is absent from the benchmark index, `/v3/verify` returns
`503 policy_unavailable` rather than falling back to a hard-coded default.
That is intentional: **a gate that silently invents its own thresholds is worse
than no gate.**

Re-measure:

```bash
python skills/vv-gate/scripts/vv_gate.py selftest   # prints pass_r2 / cov_pass / z95 / kappa_cap
```

## 3. verdict → gate mapping is fail-closed

| verdict | gate | exit | Rationale |
|---|---|---|---|
| `PASS` | `PROCEED` | 0 | R² ≥ 0.9 and coverage ≥ 0.9 |
| `MARGINAL` | `PROCEED_WITH_HUMAN_CHECK` | 3 | R² ≥ 0.7 and coverage ≥ 0.8; good enough to be worth a human's time, not good enough to act alone |
| `REFUTED` | `BLOCK_AUTONOMOUS_ACTION` | 2 | below the marginal floor |
| `ERROR` | `BLOCK_AUTONOMOUS_ACTION` | 2 | **unknown ≠ fine** |

The last row is the load-bearing one. `ERROR` blocks. Any adjudicator that maps
"could not evaluate" to "proceed" is not a gate; it is a rubber stamp with a
logging statement attached.

Exit `4` sits outside this table on purpose: it means **no verdict was
produced** (edge block or network failure). It is not a weaker `PROCEED` and it
is not a `BLOCK`. Alert/retry on it; never treat it as clearance.

Coverage is only computed when you supply `y_std`. `coverage = null` in a
response means *not evaluated*, which is **not** the same as coverage = 1.
Do not report a `PASS` without `y_std` as "well calibrated".

## 4. Provenance — the ledger can be checked, not just trusted

`GET /v3/gate` (and `python vv_gate.py ledger`) carries a `provenance` block:

```json
{
  "engine": {
    "git_commit": "1de10d634d2274ff4d8866ab899ac515d353c8a4",
    "n_modules": 51,
    "core": { "surrogate.py": "43231fdd…", "verification_gate.py": "01e84a3d…", "…": "…" },
    "core_digest": "594504b2…",
    "all_digest": "555b770c…"
  },
  "oracle": { "files": { "…": "…" }, "digest": "085076f9…" },
  "report_index_sha256": "…"
}
```

`core_digest` covers the 7 modules that actually determine a verdict
(`surrogate`, `microbiology_full`, `scenarios_extra`, `verification_gate`,
`guard`, `wet_lab_anchors`, `report_generator`); `all_digest` covers all 51
engine modules. `oracle_digest` covers the oracle definitions specifically —
so a change to the ground truth is distinguishable from a change to the scorer.

`engine_fingerprint()` reads `.git/HEAD` rather than shelling out to `git`, so
it works in build environments without git on `PATH`. `ledger_is_stale(ledger)`
compares a ledger's recorded `all_digest` against the current source; when you
see a mismatch, the ledger you are reading was built from different code than
the code you think you are trusting. Treat that as a red flag, not a warning.

## 5. The second evidence chain: wet-lab anchors

The R² chain proves the surrogate is faithful **to the oracle**. It cannot
prove the oracle matches biology. So a second, independent chain fits the
*noise-free oracle* with `scipy.optimize.least_squares` to recover implied
kinetic parameters, and grades them against literature **ranges** (multi-source,
never a point estimate):

| grade | rule | gate |
|---|---|---|
| `AGREE` | inside the literature range | `PROCEED` |
| `NEAR` | ≤ 3× off the range | `PROCEED_WITH_HUMAN_CHECK` |
| `CONTRADICTED` | > 3× off (crosses an order of magnitude) | `BLOCK_AUTONOMOUS_ACTION` |
| `UNANCHORED` | no physical counterpart exists | `NO_WET_LAB_ANCHOR` |

Current tally over the 10 anchorable scenarios: **3 AGREE / 3 NEAR /
2 CONTRADICTED / 2 UNANCHORED**. `UNANCHORED` is not a failure — most of the 62
scenarios are dimensional/mathematical test functions with no physical
counterpart, and inventing anchors for them would be worse than admitting
absence.

**The two `CONTRADICTED` entries are the most important thing on this page,
because the R² chain passes them:**

| scenario | R² chain | anchor chain | finding |
|---|---|---|---|
| `microbio_monod` | PASS (`PROCEED`) | **CONTRADICTED** (blocks) | fitted `Ks = 0.22 g/L`, which is **44×** above the literature ceiling of 0.005 g/L for E. coli on glucose |
| `micro_thermal_death` | PASS (`PROCEED`) | **CONTRADICTED** (blocks) | oracle is `kill = 0.003·(T-60)·t`, so inactivation at 60 °C is **0**; real E. coli has a finite `D60 = 25–132 s` and the model has no `z` value at all |

Read together, those rows are the argument for why two chains exist: on
`microbio_monod` the surrogate is an excellent fit to an oracle whose Ks is
physically wrong. `R² = 1.0` would have been "perfectly faithful to the wrong
physics". Neither chain alone would have caught it.

`micro_cerevisiae_ethanol` is refused differently — a **SEMANTIC_MISMATCH**
diagnosis: the second axis is labelled "ethanol product inhibition, 0–50", but
the oracle is non-monotonic on that axis with its peak at `x[1] = 30` (i.e. it
is reading `x[1]` as *temperature*, not as an inhibitor concentration). The
scenario is graded `UNANCHORED`, the mismatch is reported, and it was
**not silently patched**.

The builder deliberately does **not** copy values from scenario metadata —
that metadata was itself found to be unreliable. `microbio_monod`'s metadata
and `micro_ecoli_glucose`'s metadata disagree by 55× on Ks for the same
organism and substrate citing the same textbook. Implied parameters are always
re-derived by fitting the oracle; fits with residual > 1e-3 are marked
`FIT_FAILED` rather than reported as a parameter.

Re-measure:

```bash
python skills/vv-gate/scripts/vv_gate.py anchors               # all anchors + scenarios
python skills/vv-gate/scripts/vv_gate.py anchors microbio_monod
```

## 6. Consumer notes — measured, not guessed

### 6.1 Cloudflare User-Agent behaviour

The site sits behind a Browser-Integrity rule. Probing the same endpoint with
different UAs gave a clean split:

| User-Agent | Result |
|---|---|
| *(empty / unset)* | **403** `error code: 1010` |
| `Python-urllib/3.13` (stdlib default) | **403** `error code: 1010` |
| `python-requests/…` | 200 |
| `curl/…` | 200 |
| `node-fetch`, `axios`, `Go-http-client`, `okhttp` | 200 |
| any explicit custom UA | 200 |
| a browser UA | 200 |

So the blast radius is narrow but **exactly hits the laziest code path**: a
stdlib `urllib.request.urlopen(url)` with no `Request` object. If you
re-implement the client, set a UA. This is the single most likely reason your
integration "doesn't work" while `curl` works fine.

`vv_gate.py` sends `SwarmLabs-VVGate/1.0 (+https://swarmlabs.tools)`. On a 403
containing `1010` it retries and, if every attempt is blocked, prints an explicit
diagnosis and exits `4` — never a bare traceback, and never a verdict.

**The block is not deterministic.** This matters more than the table above: even
an *allowed* UA gets 403'd some of the time. Measured on GitHub Actions — CI run
`#23` ran four jobs, all green. Run `#24`, byte-identical `vv_gate.py` (only docs
had changed), had its two **live** jobs (`vv-gate-selftest`,
`vv-gate-server-selftest`) go red in the same minute, while the two **offline**
jobs (`lint-and-syntax`, `no-dependencies-in-gate`) stayed green both times. A
local loop of the same test passed three times in a row.

> **Correction (0.2.2, same day).** The paragraph above correctly establishes that
> the block is non-deterministic, but it was **over-applied**: the red live jobs
> were read as "1010 flakiness" when the dominant cause was a **partially landed
> deployment** on the host project. Ten consecutive deploys, each reporting
> `Uploaded 374 files`, produced **4 complete and 6 incomplete** deployments — one
> served 62 of 379 assets correctly. Pages answers a path that did not land with
> the SPA's `index.html` at status **200** `text/html`, so the incomplete deploy
> was invisible to any status-code check, and a 7-day-TTL edge cache entry holding
> a good copy made it look like ~15% flakiness rather than 100% breakage. Fix the
> deployment (byte-for-byte post-deploy gate) and the rate drops from 14.7% to
> **0.7%**. The lesson generalises past this kit: *a non-deterministic upstream
> error is a hypothesis, not a diagnosis — and "the thing I could not read" is not
> the same as "the thing that is broken".*
 So:

* one 1010 is **not** evidence that the service is down, and **not** evidence
  that your client is misconfigured;
* treat it as a transient infrastructure signal — retry, then alert;
* do not "fix" it by caching the last known verdict, and do not convert it to
  success. Both turn a gate into decoration.

### 6.2 Input validation on `/v3/verify`

| condition | response |
|---|---|
| `predictions` missing or not an array / empty | `400 bad_request` |
| count ≠ published held-out count | `400 bad_request` + `n_expected`, `n_got` |
| `y_pred` non-finite | `400 bad_request` |
| `y_std` supplied but ≤ 0 or non-finite | `400 bad_request` |
| `len(x)` ≠ scenario `dim` | `400 bad_request` |
| any `x[i]` differs from published `x[i]` by > `1e-6` | `400 bad_request` + offending `index` |
| unknown `scenario_key` | `404 unknown_scenario` + `available_count` |
| **the held-out asset could not be read** (empty body / bad JSON / non-404 status) | **`503 asset_unavailable`** + `retryable: true` |
| `GET` | `405 method_not_allowed` |
| `gate_policy` absent | `503 policy_unavailable` |

Note the row above `GET`: a read failure is **not** an unknown scenario. The
service used to collapse both into `404 unknown_scenario`, which meant it would
confidently assert that a scenario it publishes does not exist. Fail-closed on
this axis means `503 + retryable`, never a fabricated `404`. See §6.2b.

The `1e-6` alignment check exists because scoring a mis-aligned submission
would produce a confidently wrong R² — the exact failure this service is built
to refuse. Use `template` to obtain a correct `x` skeleton and only fill
`y_pred` / `y_std`.

### 6.2b Transient failures retry; verdicts do not

`vv_gate.py` retries `429 / 500 / 502 / 503 / 504`, network errors,
**`403 + error code 1010`**, and **a 2xx whose body is empty or not JSON**, with
backoff (max 4 attempts, honouring `Retry-After`). It returns `400 / 404 / 405`
**immediately**, and a `403` that does *not* carry `1010` is returned immediately
too — that one is a real edge policy rejection, not a coin flip.

That distinction is deliberate and is the difference between a useful CI gate
and a nuisance: a 400 is a verdict about your input (retrying it is pointless),
while a 429 is the service telling you to come back. A gate that goes red on a
transient rate limit teaches people to ignore red — which is worse than not
testing. `selftest` prints the transport counters so you can see when this is
happening:

```
[5] transport: 0 transient retry(ies), 0 edge block(s), 0 empty-body response(s), last_status=None
```

If you re-implement the client, copy this behaviour. Note that `503` is
ambiguous: it is also the correct response for `policy_unavailable`, and in that
case retrying will not help. Four attempts costs a few seconds, so the retry is
kept for both.

When every attempt fails, the client raises `EdgeBlocked` or `BadResponse` and
exits **`4`** — *unreachable*, i.e. **no verdict exists**. It is not a weaker
`PROCEED` and it is not a `BLOCK`.

#### The empty-body case is real, not hypothetical

Measured on CI: `GET /reports/benchmark/bio_logistic.json` intermittently
answered `200` with a zero-length body. The runner log was

```
File ".../vv_gate.py", line 133, in _get
    return json.loads(r.read().decode("utf-8"))
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

— a bare traceback pointing at our own client, which reads like a bug in the
client and is not. In the MCP channel the same anomaly came back as a **bogus
`404 unknown_scenario`**, because the server collapsed "asset absent" and "asset
unreadable" into one `null`.

So the rule your client must implement is not just "retry 5xx": **a 2xx is not
automatically an answer.** Parse it, and if there is nothing to parse, treat it
as a transport anomaly.

#### How CI uses exit `4`

The two live jobs retry **once on exit `4` and only on exit `4`**. A
behavioural regression (exit `1`, a real 4xx the API should not return) fails
immediately. There is deliberately no `continue-on-error` and no `|| true`:
those would hide genuine regressions, and mapping `4` to success would mean the
pipeline proceeds when nobody adjudicated anything. Retrying on a code that
means "no answer was produced" is the honest middle.

The retry paths are covered by **deterministic** regression tests, not just
pure-function assertions — every fake upstream is a real socket on `127.0.0.1`,
so the retry loop, the exception type and the exit code are all exercised:

```
[B3] a 200 with an EMPTY body is retried, then reported as unreachable
  ok   empty-body 200 -> exit 4 (expected 4)
  ok   retried 4x (expected 4) — an anomaly, so retry it
  ok   stderr names the anomaly instead of a bare JSONDecodeError traceback
  ok   no raw JSONDecodeError escapes to the caller
[J] the exact CI failure, reproduced deterministically (local fake edge)
  ok   403/1010 -> exit 4 (expected 4)
  ok   retried 4x (expected 4) — the block is probabilistic
  ok   stderr names the actual edge code (not a bare traceback)
  ok   stderr states that no verdict was produced
  ok   a plain 403 is NOT retried (1 hit(s)) — control case
  ok   a plain 403 is not misreported as BLOCK (exit 1)
```

The `[J]` control case matters: without it, "we retry 1010" and "we retry every
403" would look identical in the logs.

### 6.3 Endpoint map

| Endpoint | Serves |
|---|---|
| `GET /v3/benchmark` | benchmark index: `total`, `total_test_points`, `verdict_counts`, `gate_policy`, `verify_endpoint` |
| `GET /v3/benchmark/{key}` | one scenario's held-out `X`/`y`, `dim`, `test_seed` |
| `GET /v3/gate` | full gate ledger + provenance |
| `GET /v3/gate/{key}` | one scenario's gate entry |
| `GET /v3/anchors` | full anchor file (6 literature anchors + 10 scenario dual chains) |
| `GET /v3/anchors/{key}` | accepts **both** key spaces: a literature anchor (`ecoli_glucose_Ks`) or a scenario (`microbio_monod`). The scenario form returns **both chains joined**: the flat wet-lab fields plus an explicit `wet_lab` block, a `vv_gate` block pulled from the gate ledger, `chains_agree`, and a `dual_chain_note` |
| `GET /v3/reports` | report index (alias) |
| `GET /v3/openapi` | OpenAPI 3.1 document — the machine-readable contract, for frameworks that ingest tool definitions instead of prose |
| `POST /v3/verify` | dynamic adjudication (also `/v3/verify/{key}`) |

`/v3/reports` and `/v3/gate` both previously resolved to the report index —
`/v3/gate` was corrected to the ledger, and `/v3/reports` added as the
report-index alias. If you cached a mapping from before 2026-09-17, refresh it.

When a single-key lookup misses, the `404` body carries `n_available` and a
sample of `available_keys` rather than just the error string — `anchors` has two
key spaces, so a miss is the common case rather than the exception.

### The dual-chain exhibit

`GET /v3/anchors/microbio_monod` is the single most useful response to point
someone at when they ask why two chains exist:

```json
{
  "scenario_key": "microbio_monod",
  "chains_agree": false,
  "wet_lab": { "grade": "CONTRADICTED", "gate": "BLOCK_AUTONOMOUS_ACTION",
               "implied_params": { "Ks": 0.22 } },
  "vv_gate": { "verdict": "PASS", "gate": "PROCEED", "r2": 0.9997, "coverage": 1, "n_test": 40 },
  "dual_chain_note": "The two evidence chains disagree. ... Gate on the MORE CONSERVATIVE of the two."
}
```

Same scenario, same run, two independent chains, opposite conclusions — returned
together, with `chains_agree: false` making the conflict machine-detectable. A
consumer that only reads `vv_gate` would proceed into a physically wrong
inactivation/growth model. **Gate on the more conservative chain**, i.e. take
`BLOCK` here.

## 7. Baseline history — read this before quoting the gate

| date | PASS | MARGINAL | REFUTED | ERROR | note |
|---|---|---|---|---|---|
| pre-2026-09-15 | 53 | 4 | 5 | 0 | the 5 REFUTED were retained and hard-blocked, not removed |
| 2026-09-15 onward | **62** | 0 | 0 | 0 | two-stage coordinate upgrade; the log10 length scale hit the grid lower bound (0.08), which the training side handles automatically |

Verified independently across 4 seeds (248/248) after the upgrade.

**Therefore: `n_blocked = 0` today.** Do not present a non-zero block count as
evidence that the gate has teeth — it does not, on the current baseline. The
`MARGINAL` and `REFUTED` paths are exercised by the negative controls in the
table below, not by the 62 published scenarios.

Negative controls actually run against `POST /v3/verify` on the deployed
service:

| case | result |
|---|---|
| exact oracle, no `y_std` | 200 `PASS` / `PROCEED`, `r2 = 1`, `coverage = null` |
| exact oracle + `y_std = 0.05` | 200 `PASS` / `PROCEED`, `coverage = 1`, `kappa = 1` |
| 1.5× deviation, no `y_std` | 200 `REFUTED` / `BLOCK`, `r2 = -4.4876` |
| 1.5× deviation + `y_std = 0.02` | 200 `REFUTED` / `BLOCK`, `coverage = 0`, `kappa = 3.341` |
| 2% deviation + `y_std = 0.05` | 200 `PASS` / `PROCEED`, `r2 = 0.9912`, `coverage = 1.0` |

These are the numbers to cite when asked whether the gate can actually refuse.

## 8. Honest boundaries

- **No company entity, bus factor = 1, pre-revenue, 0 GitHub stars.** The
  engineering is checkable — the digests above are verifiable, and `selftest`
  is live — but treat the project's *organisational* maturity as unproven.
- **The gate is only as good as its oracle.** Where the anchor chain disagrees
  with the R² chain (Section 5), believe the disagreement, not the PASS.
- **62 scenarios is a curated set, not a benchmark suite.** Passing it is not
  evidence of general scientific competence.
- **Scenario metadata is not a trusted source.** Any parameter you see in
  scenario metadata should be treated as unreliable until re-derived by
  fitting; `microbio_monod` and `micro_ecoli_glucose` disagree by 55× on the
  same quantity.
- `UNANCHORED` is reported as `NO_WET_LAB_ANCHOR`, never folded into a pass.
