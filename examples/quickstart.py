"""Minimal end-to-end example for the SwarmLabs Engine Kit.

Replace BASE_URL with your deployed SwarmLabs engine endpoint. Works against
any deployment exposing the /api/v2/ surface.
"""

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
