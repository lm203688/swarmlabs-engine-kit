"""Offline reference schemas for the SwarmLabs engine.

These mirror the server-side ``ENGINE_CATEGORIES`` / ``CATEGORY_PARAMS`` so the
client can offer helpful defaults and validation without a network call. They
are a representative subset derived from the deployed engine definitions and are
kept read-only here.
"""

from typing import Dict, List, Optional

# Category -> list of example engine ids (representative, not exhaustive).
ENGINE_CATEGORIES: Dict[str, list] = {
    "Chemistry": ["suzuki", "heck", "sonogashira", "buchwald", "hydrogenation"],
    "Environment": ["photocatalysis", "co2", "water_splitting", "ozonation"],
    "Energy": ["battery_li_ion", "fuel_cell", "nuclear_fission", "ammonia"],
    "Materials": ["coating", "sintering", "quantum_dot", "crystal", "corrosion"],
    "Biology": ["fermentation_ethanol", "enzymatic_hydrolysis", "protein_denaturation"],
    "Separation": ["reverse_osmosis", "nanofiltration", "distillation", "adsorption"],
    "Analysis": ["titration_acid_base", "spectrophotometry", "mass_spec", "chromatography"],
    "Pharma": ["tablet_compression", "dissolution", "pk_modeling", "release_fit"],
    "Electrochemistry": ["electroplating", "electrodialysis", "anodizing"],
    "CFD": ["cfd_cylinder", "cfd_lid_cavity", "cfd_aneurysm", "cfd_vortex"],
    "HeatTransfer": ["heat_2d", "heat_chip", "heat_exchanger"],
    "Structural": ["struct_beam", "struct_plate", "struct_bracket", "struct_topopt"],
    "PDE": ["pde_solver", "pde_inverse", "pde_param_id"],
    "Quantum": ["qaoa_maxcut", "vqe_h2", "quantum_circuit_fidelity"],
    "BrainScience": ["neural_firing_rate", "synaptic_stdp", "network_smallworld", "decoding_accuracy"],
}

CATEGORIES = list(ENGINE_CATEGORIES.keys())

# Required / default / unit hints per category (representative subset).
CATEGORY_PARAMS: Dict[str, dict] = {
    "Chemistry": {
        "required": ["temperature_C", "catalyst_loading", "time_h"],
        "defaults": {"temperature_C": 80, "catalyst_loading": 1.0, "time_h": 4},
        "units": {"temperature_C": "°C", "catalyst_loading": "mol%", "time_h": "h"},
    },
    "Energy": {
        "required": ["temperature_C", "time_h"],
        "defaults": {"temperature_C": 25, "time_h": 4},
        "units": {"temperature_C": "°C", "time_h": "h"},
    },
    "Quantum": {
        "required": ["bond_length_A"],
        "defaults": {"bond_length_A": 0.74},
        "units": {"bond_length_A": "Å"},
    },
    "BrainScience": {
        "required": ["stimulation_hz"],
        "defaults": {"stimulation_hz": 40},
        "units": {"stimulation_hz": "Hz"},
    },
}


def category_of(engine: str) -> Optional[str]:
    """Best-effort category lookup from the offline reference map."""
    for cat, engines in ENGINE_CATEGORIES.items():
        if engine in engines:
            return cat
    return None
