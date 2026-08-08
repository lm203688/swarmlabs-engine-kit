"""SwarmLabs Engine Kit — open-source client SDK.

Client side of the SwarmLabs physics-informed scientific experiment
automation engine. See README.md for an overview.
"""

from .client import SwarmLabsClient, SwarmLabsError
from .schemas import ENGINE_CATEGORIES, CATEGORY_PARAMS, CATEGORIES

__version__ = "0.1.0"
__all__ = [
    "SwarmLabsClient",
    "SwarmLabsError",
    "ENGINE_CATEGORIES",
    "CATEGORY_PARAMS",
    "CATEGORIES",
]
