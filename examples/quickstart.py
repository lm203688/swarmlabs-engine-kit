"""Minimal end-to-end example for the SwarmLabs Engine Kit.

Replace BASE_URL with your deployed SwarmLabs engine endpoint. Works against
any deployment exposing the /api/v2/ surface.

Runs from a fresh clone with no install: if `swarmlabs_engine` is not already
importable (i.e. `pip install -e .` was not run), the in-repo `src/` layout is
added to sys.path below. Otherwise this file dies on line 1 of the import and
makes "clone and try it" look broken.
"""

import os
import sys

try:  # installed package
    from swarmlabs_engine import SwarmLabsClient
except ModuleNotFoundError:  # fresh clone: use the in-repo src/ layout
    _SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    if os.path.isdir(_SRC) and _SRC not in sys.path:
        sys.path.insert(0, _SRC)
    from swarmlabs_engine import SwarmLabsClient


BASE_URL = "https://your-swarmlabs-engine.example.com"


def main() -> None:
    client = SwarmLabsClient(base_url=BASE_URL)

    # 1) Discover what the engine can do.
    info = client.list_engines()
    print(f"Engines: {info.get('engines')}  Physics models: {info.get('physics_models')}")

    # 2) Run a real physics-informed prediction (H2 dissociation via VQE).
    result = client.run("vqe_h2", {"bond_length_A": 0.74})
    print(f"Predicted energy: {result['result']} +/- {result['uncertainty']}")
    print(f"Empirical-validated datapoints: {result.get('empirical_validated')}")
    print(f"Literature-validated: {result.get('literature_validated')}")

    # 3) Sweep a parameter to understand the trend (free tier).
    sweep = client.sweep("vqe_h2", {"bond_length_A": 0.74}, n=5)
    print(f"Sweep points returned: {len(sweep.get('points', []))}")


if __name__ == "__main__":
    main()
