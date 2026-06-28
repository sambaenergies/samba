# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""SAMBA scenario schema -- public re-exports.

All imports of the form ''from samba.scenario.models import Scenario'' (and
any other model class) continue to work unchanged through this package
''__init__.py''.

Internal layout
---------------
''_tariff.py''      -- TouPeriod, TierLevel, SeasonalRate, SeasonalTiers,
                      BuyRate, SellRate, ServiceCharge, Tariff
''_components.py''  -- PV, KiBaMParams, Battery, WindTurbine, DieselGenerator,
                      Inverter, Grid, EV, Components
''_scenario.py''    -- Project, Location, Weather, Load, Constraints,
                      Objective, Scenario
"""

from __future__ import annotations

from samba.scenario.models._components import (
    EV,
    PV,
    Battery,
    BatteryDegradation,
    Components,
    DieselGenerator,
    GasSeasonalRate,
    GasSupply,
    GasTariff,
    Grid,
    HeatPump,
    Inverter,
    KiBaMParams,
    ThermalStorage,
    WindTurbine,
)
from samba.scenario.models._scenario import (
    Constraints,
    Load,
    Location,
    Objective,
    Project,
    Scenario,
    ThermalLoad,
    Weather,
)
from samba.scenario.models._tariff import (
    NEM,
    BuyRate,
    DemandCharge,
    SeasonalRate,
    SeasonalTiers,
    SellRate,
    ServiceCharge,
    Tariff,
    TierLevel,
    TouPeriod,
)

# Trigger model_rebuild() so Pydantic resolves any forward references across
# the sub-module boundary (required for models that reference each other).
Scenario.model_rebuild()

__all__ = [
    # tariff
    "TouPeriod",
    "TierLevel",
    "SeasonalRate",
    "SeasonalTiers",
    "BuyRate",
    "SellRate",
    "ServiceCharge",
    "DemandCharge",
    "NEM",
    "Tariff",
    # components
    "PV",
    "KiBaMParams",
    "Battery",
    "BatteryDegradation",
    "WindTurbine",
    "DieselGenerator",
    "Inverter",
    "Grid",
    "EV",
    "HeatPump",
    "ThermalStorage",
    "GasSeasonalRate",
    "GasTariff",
    "GasSupply",
    "Components",
    # scenario
    "Project",
    "Location",
    "Weather",
    "ThermalLoad",
    "Load",
    "Constraints",
    "Objective",
    "Scenario",
]
