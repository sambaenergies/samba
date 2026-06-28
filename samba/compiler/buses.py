# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Bus container and factory for the compiled energy system.

All bus creation is authoritative here -- no bus nodes are created anywhere
else in the compiler.  Component builders receive pre-built bus references via
the :class:'BusSet' returned by :func:'build_buses'.

DC bus creation rule (O2 -- domain-model.md Sec.Bus Architecture):
    ''dc_bus'' is created if ''pv.enabled'' **or** ''battery.enabled''.
    A PV-only scenario (no battery) still needs ''dc_bus'' for the
    PV -> Inverter flow.  A pure-grid/diesel scenario has no DC components
    and therefore no ''dc_bus''; the inverter is not built in that case.

Fuel bus (diesel):
    The diesel generator builder (''DieselBuilder'') creates its own
    ''fuel_bus'' internally as part of the builder's node group.  It is
    therefore NOT created here.  The :class:'BusSet' carries a ''fuel''
    field that is populated by the compiler after DieselBuilder runs (v4+
    refactor scope).  For now, ''fuel'' is always ''None'' in the returned
    ''BusSet''; callers that need the fuel bus should look it up from the
    assembled energy system via ''es.groups.get("fuel_bus")''.

Thermal buses:
    Delegated to :func:'samba.thermal.buses.build_thermal_buses'.
    ''heat_bus'', ''cool_bus'', and ''gas_bus'' are conditional on the
    enabled thermal components following ADR-001 label conventions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from samba.thermal.buses import ThermalBusSet, build_thermal_buses

if TYPE_CHECKING:
    from samba.scenario.models import Scenario

__all__ = ["BusSet", "build_buses"]


@dataclass
class BusSet:
    """All oemof buses for a compiled scenario.

    ''ac'' is always present.  All other fields default to ''None'' and are
    populated by :func:'build_buses' if the corresponding sub-system is active.

    Attributes
    ----------
    ac:
        AC system bus -- always created.
    dc:
        DC system bus -- present if PV or battery is enabled (O2 rule).
    fuel:
        Diesel fuel bus -- present if diesel generator is enabled.
    thermal:
        Thermal bus container (:class:'~samba.thermal.buses.ThermalBusSet').
    """

    ac: Any  # solph.Bus -- always present
    dc: Any | None = None  # solph.Bus | None
    fuel: Any | None = None  # solph.Bus | None
    thermal: ThermalBusSet = field(default_factory=ThermalBusSet)


def build_buses(scenario: Scenario, energy_system: Any) -> BusSet:
    """Create all scenario buses, add them to the energy system, and return a BusSet.

    Buses are added to *energy_system* directly inside this function so that
    the caller (the compiler) only needs to add component nodes afterward.

    Parameters
    ----------
    scenario:
        Validated scenario configuration.
    energy_system:
        The ''solph.EnergySystem'' being assembled.  Buses are added in-place.

    Returns
    -------
    BusSet
        Populated bus container; component builders use its fields instead of
        constructing bus references independently.
    """
    import oemof.solph as solph

    c = scenario.components

    # AC bus -- always present
    ac_bus = solph.Bus(label="ac_bus")
    energy_system.add(ac_bus)

    # DC bus -- only if there are DC-coupled components (PV or battery)
    dc_bus: Any | None = None
    pv_on = c.pv is not None and c.pv.enabled
    batt_on = c.battery is not None and c.battery.enabled
    if pv_on or batt_on:
        dc_bus = solph.Bus(label="dc_bus")
        energy_system.add(dc_bus)

    # NOTE: diesel fuel_bus is NOT created here.
    # DieselBuilder creates its own fuel_bus internally and returns it as part
    # of its node group.  BusSet.fuel remains None for Phase 19; future
    # refactoring (Phase 20+) should migrate DieselBuilder to accept an
    # externally-supplied bus.

    # Thermal buses (heat_bus, cool_bus, gas_bus) -- delegated to thermal module
    thermal = build_thermal_buses(scenario)
    for bus in (thermal.heating, thermal.cooling, thermal.gas):
        if bus is not None:
            energy_system.add(bus)

    return BusSet(ac=ac_bus, dc=dc_bus, thermal=thermal)
