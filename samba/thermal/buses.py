# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Thermal bus dataclass and factory function.

Bus labels (ADR-001 canonical):
    - ''"heat_bus"''  -- heating energy in kWh_th
    - ''"cool_bus"''  -- cooling energy in kWh_th (positive = cooling delivered)
    - ''"gas_bus"''   -- natural gas in kWh_th (LHV basis)

Creation rules:
    - ''heat_bus'' is created when heat pump is enabled OR gas supply is enabled.
    - ''cool_bus'' is created when heat pump is enabled (HP is the only cooling
      source in v3; Phase 20 adds the HP which can run in cooling-only or dual mode).
    - ''gas_bus''  is created when gas supply is enabled.
    - When no thermal components are enabled, returns ''ThermalBusSet(None, None, None)''
      so that electrical-only scenarios are structurally identical to v2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from samba.scenario.models import Scenario

__all__ = ["ThermalBusSet", "build_thermal_buses"]


@dataclass
class ThermalBusSet:
    """Container for conditional thermal bus objects.

    All three fields default to ''None''; a field is non-''None'' only when the
    corresponding energy carrier is active in the compiled scenario.

    Use the ''has_*'' properties in builders and the extractor to guard
    against operating on ''None'' buses.
    """

    heating: Any | None = None  # solph.Bus | None -- "heat_bus"
    cooling: Any | None = None  # solph.Bus | None -- "cool_bus"
    gas: Any | None = None  # solph.Bus | None -- "gas_bus"

    @property
    def has_heating(self) -> bool:
        """True if a heating bus was created for this scenario."""
        return self.heating is not None

    @property
    def has_cooling(self) -> bool:
        """True if a cooling bus was created for this scenario."""
        return self.cooling is not None

    @property
    def has_gas(self) -> bool:
        """True if a gas bus was created for this scenario."""
        return self.gas is not None


def build_thermal_buses(scenario: Scenario) -> ThermalBusSet:
    """Create thermal buses conditionally based on enabled components.

    Returns ''ThermalBusSet(None, None, None)'' if no thermal components are
    enabled (e.g. any v1/v2 electrical-only scenario).

    The gas bus is pre-allocated here so that the Phase 23 ''GasSupplyBuilder''
    receives it via ''bus_set.thermal.gas'' rather than independently creating
    a bus node.  All bus creation is authoritative in this module.

    Parameters
    ----------
    scenario:
        Validated scenario configuration.

    Returns
    -------
    ThermalBusSet
        Populated with ''solph.Bus'' objects for active carriers; ''None'' for
        inactive ones.
    """
    import oemof.solph as solph

    c = scenario.components
    hp = c.heat_pump
    gas = c.gas_supply

    need_heating = (hp is not None and hp.enabled) or (gas is not None and gas.enabled)
    # HP is the only cooling source in v3; cooling bus exists iff HP is enabled.
    need_cooling = hp is not None and hp.enabled
    need_gas = gas is not None and gas.enabled

    heat_bus = solph.Bus(label="heat_bus") if need_heating else None
    cool_bus = solph.Bus(label="cool_bus") if need_cooling else None
    gas_bus = solph.Bus(label="gas_bus") if need_gas else None

    return ThermalBusSet(heating=heat_bus, cooling=cool_bus, gas=gas_bus)
