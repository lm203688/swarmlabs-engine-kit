# Contributing

Thanks for looking. This is a one-maintainer project — please keep that in mind
for anything time-sensitive.

## Before you open a PR

- **Bugs:** include a command that reproduces it. `python
  skills/vv-gate/scripts/vv_gate.py selftest` is the fastest way to show whether
  the deployed service is healthy at all.
- **Behaviour changes to the gate:** read
  [`skills/vv-gate/references/gate-semantics.md`](skills/vv-gate/references/gate-semantics.md)
  first. The verdict→gate mapping and the fail-closed rule are not negotiable
  (see [`GOVERNANCE.md`](GOVERNANCE.md#decision-making)).
- **New features in `skills/vv-gate/`:** must remain **Python 3.8+ stdlib
  only**. No numpy, no requests, no third-party imports. This is a hard
  invariant: the value of the gate is that it runs inside someone else's
  harness with no build step. A PR that adds a dependency there will be
  rejected regardless of merit.

## Local checks

```bash
# 1. syntax, all Python in the repo
python -m compileall -q src mcp skills examples

# 2. stdlib-only invariant inside skills/vv-gate/ (the CI-enforced hard line)
python skills/vv-gate/tests/check_stdlib_only.py

# 3. the live smoke test (network — it talks to the deployed service)
python skills/vv-gate/tests/run_selftest.py

# 4. the shipped client's own smoke test
python skills/vv-gate/scripts/vv_gate.py selftest
```

`check_stdlib_only.py` fails on any non-stdlib import under `skills/vv-gate/`.
It is deliberately mechanical: a third-party import there would not even show
up in the live smoke test on a machine that happens to have the dependency, so
review is not a sufficient check.

`tests/run_selftest.py` asserts the things that tend to silently rot:
the verdict→gate mapping is fail-closed, `ERROR` has no permissive exit code,
`gate_policy` is published, the ledger is provenance-annotated, an unfilled
submission is refused, and the oracle round-trips to `r2 == 1`.

## Commit messages

Conventional-ish, one line, imperative:

```
fix(vv-gate): resolve scenario-level anchor keys (scenarios is a list, not a map)
feat(vv-gate): expose available_keys on 404 so consumers stop guessing
docs(gate-semantics): correct the block-count claim (baseline is 0, not 5)
```

## Adding a Skill

A Skill lives in `skills/<name>/` and must contain:

```
skills/<name>/
  SKILL.md                 # agentskills.io frontmatter: name, description, license, allowed-tools, metadata
  scripts/<entrypoint>     # runnable, dependency-free preferred
  references/<topic>.md    # anything long enough to bloat SKILL.md
  tests/                   # a runnable check, even if it is a live smoke test
```

Keep `SKILL.md` under ~500 lines and push detail into `references/`. The
`description` field is what an agent sees when deciding whether to load the
skill — write it as *when to use this*, not as a summary of what it contains.

Register it in `skills/skill_catalog.json` in the same PR.

## Documentation claims

If you write a number into a doc, state the command that reproduces it. Numbers
in this repository are load-bearing — `gate-semantics.md` is cited by external
consumers when deciding whether to trust the gate — so an unverifiable
statistic is treated as a bug.

## Reporting security issues

Not in a public issue. See [`SECURITY.md`](SECURITY.md).
