# SwarmLabs Engine Kit

> Open-source client SDK, MCP server, and Skill catalog for the **SwarmLabs
> physics-informed multi-agent scientific experiment automation engine**.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

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

## What's inside

| Path | What |
|---|---|
| `src/swarmlabs_engine/` | Python client SDK (`SwarmLabsClient`) |
| `mcp/server.py` | Reference MCP server exposing engine calls as tools |
| `skills/skill_catalog.json` | Machine-readable catalog of the 4 core Skills |
| `examples/quickstart.py` | Minimal end-to-end example |
| `docs/API.md` | Endpoint reference |

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

`skills/skill_catalog.json` describes the 4 core Skills that compose a
SwarmLabs multi-agent workflow:

1. **PhysicsPredictSkill** — call the real engine.
2. **ExperimentDesignSkill** — turn a goal into a parameter plan.
3. **ActiveLearningSkill** — pick the next most informative experiment point.
4. **ReportGenerationSkill** — emit an auditable report.

These are the building blocks of the SwarmLabs "Planner → Executor →
Verifier" agent loop.

## License

[MIT](LICENSE).
