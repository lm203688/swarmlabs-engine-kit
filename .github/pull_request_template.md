## What this changes

<!-- One or two sentences. If it fixes an issue, link it. -->

## Checks

- [ ] `python -m compileall -q src mcp skills examples` passes
- [ ] `python skills/vv-gate/tests/run_selftest.py` passes (network test against the deployed service)
- [ ] No new third-party imports inside `skills/vv-gate/` (stdlib only is a hard invariant)

## If this touches the gate

- [ ] The verdict→gate mapping is still fail-closed; `ERROR` still maps to `BLOCK_AUTONOMOUS_ACTION`
- [ ] A missing or malformed `gate_policy` still returns a refusal, not a default
- [ ] "Not evaluated" is still distinguishable from "passed" (e.g. `coverage: null` ≠ `coverage: 1`)
- [ ] Any number written into the docs comes with the command that reproduces it

## If this changes a published result

- [ ] The previous result is still recorded, not overwritten

<!-- Published failures stay published. Where the two evidence chains disagree
     (see gate-semantics.md §5), both remain reported — removing the
     disagreeing chain is not an acceptable change. -->
