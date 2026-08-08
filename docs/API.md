# SwarmLabs Engine API Reference

All endpoints are served under `/api/v2/`. The base URL is **your** deployed
SwarmLabs engine endpoint (this kit is the open-source client side).

## `GET` / `POST` `/api/v2/list`

Returns engine coverage.

```json
{
  "engines": 163,
  "physics_models": 16,
  "categories": ["Chemistry", "Energy", "Quantum", "BrainScience", "..."]
}
```

## `POST` `/api/v2/run/{engine}`

Run a real physics-informed prediction.

**Body:** engine parameters as JSON, e.g. `{"bond_length_A": 0.74}` for `vqe_h2`.

**Response (abridged):**

```json
{
  "result": -1.13,
  "secondary_result": null,
  "uncertainty": 0.02,
  "epistemic_uncertainty": 0.0,
  "model": "modelQuantum",
  "category": "Quantum",
  "empirical_validated": 0,
  "literature_validated": 1,
  "paper_reference": "doi:10.1063/1.XXXXXX"
}
```

- `uncertainty` — aleatoric / model uncertainty of the prediction.
- `epistemic_uncertainty` — distance from validated parameter space (higher =
  less trustworthy).
- `empirical_validated` — count of real published experiment datapoints the
  model is validated against.
- `literature_validated` — count of real papers the model is validated against.

> Honesty-first: these are **never** a single inflated "validated" count, and
> `v2/pi` returns the **real** physics model (not a constant placeholder).

## `POST` `/api/v2/pi/{engine}`

Physics-informed variant. Same honest models as `v2/run`; provided as a
semantically explicit entry point for agents that separate "physics-informed"
calls from generic runs.

## `POST` `/api/v2/sweep/{engine}`

Parameter sweep for trend analysis. Free tier (no credits consumed). Body
includes the base `params` plus `_n` (number of sample points).

## `POST` `/api/v2/multifidelity`

Cross-engine multi-fidelity query. Body: `{"engines": [...], "params": {...}}`.

## `POST` `/api/v2/measure/{engine}`

Record a real measurement to compare against a prediction. Body includes the
base `params` plus `measured_value`. Returns a comparison vs the predicted value.

## Error contract

Non-2xx responses return JSON of the form:

```json
{ "error": "Unknown engine: foo", "available": ["vqe_h2", "suzuki", "..."] }
```
