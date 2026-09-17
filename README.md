# SwarmLabs Engine Kit

> Open-source client SDK, MCP server, and Skill catalog for the **SwarmLabs
> physics-informed multi-agent scientific experiment automation engine**.

[![CI](https://github.com/lm203688/swarmlabs-engine-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/lm203688/swarmlabs-engine-kit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](pyproject.toml)

SwarmLabs is an open infrastructure that turns **multidisciplinary scientific
experiments** (chemistry, energy, materials, environment, biology, pharma,
quantum computing, brain science, CFD, structural mechanics, …) into
**callable, auditable physics-informed predictions** served over a small HTTP
API. This repository is the **open-source developer toolkit** around that
engine — it does not contain the proprietary physics models, only the
interface, reference integrations, and honesty-first contracts that let any
agent or application consume the engine safely.

## Why this exists

Scientific-AI tooling is flooded with demos that return confident-but-fake
numbers. SwarmLabs takes the opposite stance — **honesty-first**:

- Every prediction reports an `uncertainty` and, where applicable, an
  `epistemic_uncertainty` (how far the request is from validated parameter
  space).
- Validation is split into `empirical_validated` (matched to real published
  experiment data) and `literature_validated` (matched to a real paper), never
  a single inflated "validated" count.
- The `v2/pi` (physics-informed) endpoint returns the **real** physics model —
  it does not return a constant placeholder.

This kit makes those guarantees easy to build on top of, from a Python script,
an MCP-compatible agent runtime, or a no-code agent builder.

It also ships something most scientific-AI toolkits do not: a **verification
gate you do not control** — an independent adjudicator that can answer *"no"*
to your agent's claim, and block it. See
[`skills/vv-gate/`](skills/vv-gate/SKILL.md).

## What's inside

| Path | What |
|---|---|
| `src/swarmlabs_engine/` | Python client SDK (`SwarmLabsClient`) |
| `mcp/server.py` | Reference MCP server exposing engine calls as tools |
| `skills/vv-gate/` | **Independent V&V gate** — zero-dep client + SKILL.md + semantics reference |
| `skills/skill_catalog.json` | Machine-readable catalog of the core Skills |
| `examples/quickstart.py` | Minimal end-to-end example |
| `docs/API.md` | Endpoint reference |

## V&V gate — an adjudicator you don't control

> **Reproducible ≠ valid.** A fully reproducible experiment can be fully wrong.
> Git already sells reproducibility. What's missing is adjudication.

`skills/vv-gate/scripts/vv_gate.py` is a single stdlib-only file that answers
two different questions, and returns a **real exit code** so it can be a CI
hard gate rather than a dashboard:

| Question | Command | Where the truth lives |
|---|---|---|
| What is the current trust state of scenario X? | `check X` | vendor's published gate ledger |
| Are **my** predictions on this held-out set correct? | `verify X --pred p.json` | held-out set whose **y we hold**, you don't |

```bash
python skills/vv-gate/scripts/vv_gate.py selftest
python skills/vv-gate/scripts/vv_gate.py scenarios
python skills/vv-gate/scripts/vv_gate.py template microbio_monod -o preds.json
#   ... fill preds.json with your y_pred (and optionally y_std = your 1-sigma)
python skills/vv-gate/scripts/vv_gate.py verify microbio_monod --pred preds.json
#   exit 0 = PROCEED | 3 = needs human sign-off | 2 = BLOCK the autonomous action
```

Zero dependencies (no numpy), no API key, no engine clone. `ERROR` maps to
`BLOCK`, not to `PROCEED` — a gate that treats "could not evaluate" as "fine" is
a rubber stamp.

The findings are published, including the ones that go against us: the R² chain
passes all 62 scenarios, while the **independent wet-lab anchor chain flags two
of them as physically `CONTRADICTED`** (e.g. `microbio_monod`'s fitted
`Ks = 0.22 g/L` sits 44× above the literature ceiling for E. coli on glucose).
Two chains, because one is not enough — details in
[`references/gate-semantics.md`](skills/vv-gate/references/gate-semantics.md).

**Consumer gotcha worth reading before you write your own client:** Cloudflare
rejects requests with *no* `User-Agent` and with the stdlib default
`Python-urllib/3.x` (`403 error code: 1010`). `curl`, `requests`, `node-fetch`,
`axios`, Go and any explicit UA are fine. So `urllib.request.urlopen(url)` with
no `Request` is the one thing that fails.


## Install

```bash
pip install swarmlabs-engine-kit
```

Or use it directly from source:

```bash
git clone https://github.com/lm203688/swarmlabs-engine-kit.git
cd swarmlabs-engine-kit
pip install -e .
```

## Quick start

```python
from swarmlabs_engine import SwarmLabsClient

# Point the client at YOUR deployed SwarmLabs engine endpoint.
client = SwarmLabsClient(base_url="https://your-swarmlabs-engine.example.com")

# List available engines
info = client.list_engines()
print(info["engines"], "engines across", info["physics_models"], "physics models")

# Run a real physics-informed prediction (e.g. H2 dissociation via VQE)
result = client.run("vqe_h2", {"bond_length_A": 0.74})
print(result["result"], "+/-", result["uncertainty"])
```

See [`examples/quickstart.py`](examples/quickstart.py) for a fuller walkthrough.

## Engine API surface (summary)

All endpoints are served under `/api/v2/`.

| Method | Path | Purpose |
|---|---|---|
| `GET` / `POST` | `/api/v2/list` | List engines + physics-model coverage |
| `POST` | `/api/v2/run/{engine}` | Run a real physics-informed prediction |
| `POST` | `/api/v2/pi/{engine}` | Physics-informed variant (same honest models) |
| `POST` | `/api/v2/sweep/{engine}` | Parameter sweep for trend analysis |
| `POST` | `/api/v2/multifidelity` | Multi-fidelity cross-engine query |
| `POST` | `/api/v2/measure/{engine}` | Record a real measurement to compare vs prediction |

> The engine deployment URL is provided by you. This kit is the client side and
> works against any SwarmLabs engine deployment that exposes the `/api/v2/`
> surface.

## MCP integration

The reference MCP server turns engine calls into standard MCP tools so any
MCP-aware agent (Claude Desktop, Cursor, custom runtimes) can use SwarmLabs as
a trusted scientific-compute tool:

```bash
python -m mcp.server --base-url https://your-swarmlabs-engine.example.com
```

It exposes `swarmlabs_run`, `swarmlabs_list`, and `swarmlabs_sweep` tools with
explicit input schemas and the same honesty-first result contract.

## Skill catalog

`skills/skill_catalog.json` describes the core Skills that compose a SwarmLabs
multi-agent workflow:

1. **PhysicsPredictSkill** — call the real engine.
2. **ExperimentDesignSkill** — turn a goal into a parameter plan.
3. **ActiveLearningSkill** — pick the next most informative experiment point.
4. **ReportGenerationSkill** — emit an auditable report.
5. **vv-gate** — Adjudicate a numeric claim against held-out ground truth and
   literature anchors, and return a blocking gate. This one is a standalone
   agentskills.io-format Skill (`skills/vv-gate/SKILL.md`), loadable by Claude
   Code, Cursor, Codex, Gemini CLI and any harness that reads that spec.

These are the building blocks of the SwarmLabs "Planner → Executor →
Verifier" agent loop. Skills 1–4 are the loop; skill 5 is the thing that can
refuse it.

## Status — read this before trusting anything above

Honest state of the project, because you are being asked to depend on it:

| Signal | State |
|---|---|
| Engineering verifiability | **checkable** — engine/oracle digests are published, `selftest` is live, negative controls are documented |
| Company entity | **none** (no legal entity) |
| Bus factor | **1** |
| Revenue | **pre-revenue** |
| GitHub stars | **0** |

The engineering is reproducible from your side. The *organisation* is not yet
proven, and nothing in this repository should be read as implying otherwise.

## License

[MIT](LICENSE).
