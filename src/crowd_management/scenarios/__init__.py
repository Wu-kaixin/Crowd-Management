"""Known-environment scenarios for ABCG Step 1."""

from .base import Scenario
from .rectangular import BoundaryOpening, RectangularScenario
from .registry import build_scenario, register_scenario, registered_scenario_types

__all__ = [
    "BoundaryOpening",
    "RectangularScenario",
    "Scenario",
    "build_scenario",
    "register_scenario",
    "registered_scenario_types",
]
