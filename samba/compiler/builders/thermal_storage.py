# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Thermal buffer storage builder for oemof-solph (Phase 21).

Creates one (heating) or two (heating + cooling) ``solph.components.GenericStorage``
nodes on their respective thermal buses.

oemof-solph >= 0.6.1 API notes
-------------------------------
- Fixed sizing:   ``nominal_capacity=<float>`` on the storage; flows carry a
  finite ``nominal_capacity`` equal to the max charge/discharge power.
- Investment mode: ``nominal_capacity=solph.Investment(...)`` on the storage;
  input/output flows each carry ``nominal_capacity=solph.Investment()``
  (zero ep_costs) so oemof can link the flow investment to the storage
  investment (A5 coupling requirement).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import oemof.solph as solph

from samba.compiler.annualize import ep_costs as _ep_costs
from samba.compiler.annualize import real_discount_rate as _real_rate

if TYPE_CHECKING:
    from samba.compiler.buses import BusSet
    from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["ThermalStorageBuilder"]


class ThermalStorageBuilder:
    """Builds oemof ``GenericStorage`` node(s) for thermal buffer storage."""

    def build(
        self,
        scenario: Scenario,
        bus_set: BusSet,
    ) -> list[Any]:
        """Return oemof nodes for thermal storage.

        Parameters
        ----------
        scenario:
            Validated scenario; ``scenario.components.thermal_storage`` must
            not be ``None`` and must be enabled.
        bus_set:
            Bus container; ``bus_set.thermal.heating`` must exist. If
            ``include_cooling_storage=True`` then ``bus_set.thermal.cooling``
            must also exist.

        Returns
        -------
        list of solph.network.Node
            One node (heating only) or two nodes (heating + cooling).
        """
        ts = scenario.components.thermal_storage
        if ts is None or not ts.enabled:
            raise ValueError(
                "ThermalStorageBuilder.build called but "
                "scenario.components.thermal_storage is not enabled"
            )

        heat_bus = bus_set.thermal.heating
        if heat_bus is None:
            raise ValueError(
                "ThermalStorage requires a heating bus.  Enable heat_pump or "
                "gas_supply so the heating bus is created."
            )

        proj = scenario.project
        r_real = _real_rate(proj.discount_rate_nominal, proj.inflation_rate)
        annual_cost = _ep_costs(ts.capex_per_kwh_th, r_real, ts.lifetime_years)

        nodes: list[Any] = []

        # ------------------------------------------------------------------
        # Heating storage node
        # ------------------------------------------------------------------
        nodes.append(
            self._build_one(
                label="thermal_storage_heating",
                bus=heat_bus,
                ts=ts,
                capacity_kwh_th=ts.capacity_kwh_th,
                capacity_min=ts.capacity_min_kwh_th,
                capacity_max=ts.capacity_max_kwh_th,
                charge_max=ts.charge_power_max_kw_th,
                discharge_max=ts.discharge_power_max_kw_th,
                annual_cost=annual_cost,
            )
        )
        log.debug(
            "thermal_storage_heating: sizing=%s, loss_rate=%.4f /h",
            ts.sizing,
            ts.loss_rate_per_hour,
        )

        # ------------------------------------------------------------------
        # Optional cooling storage node
        # ------------------------------------------------------------------
        if ts.include_cooling_storage:
            cool_bus = bus_set.thermal.cooling
            if cool_bus is None:
                raise ValueError(
                    "Cooling storage requires a cooling bus.  Set "
                    "heat_pump.mode to 'cooling_only' or 'both'."
                )
            nodes.append(
                self._build_one(
                    label="thermal_storage_cooling",
                    bus=cool_bus,
                    ts=ts,
                    capacity_kwh_th=ts.cooling_capacity_kwh_th,
                    capacity_min=0.0,
                    capacity_max=ts.cooling_capacity_max_kwh_th,
                    charge_max=ts.charge_power_max_kw_th,
                    discharge_max=ts.discharge_power_max_kw_th,
                    annual_cost=annual_cost,
                )
            )
            log.debug("thermal_storage_cooling: sizing=%s", ts.sizing)

        log.info(
            "ThermalStorageBuilder: built %d node(s), sizing=%s",
            len(nodes),
            ts.sizing,
        )
        return nodes

    # ------------------------------------------------------------------
    # Internal: build a single GenericStorage node
    # ------------------------------------------------------------------
    def _build_one(
        self,
        *,
        label: str,
        bus: Any,
        ts: Any,
        capacity_kwh_th: float | None,
        capacity_min: float,
        capacity_max: float,
        charge_max: float | None,
        discharge_max: float | None,
        annual_cost: float,
    ) -> Any:
        """Construct and return one ``solph.components.GenericStorage``."""
        if ts.sizing == "investment":
            nominal_capacity: Any = solph.Investment(
                minimum=capacity_min,
                maximum=capacity_max,
                ep_costs=annual_cost,
            )
            charge_flow: Any = solph.Flow(nominal_capacity=solph.Investment())
            discharge_flow: Any = solph.Flow(nominal_capacity=solph.Investment())
        else:
            # Fixed sizing -- capacity must not be None (validated by schema)
            cap = float(capacity_kwh_th)  # type: ignore[arg-type]
            nominal_capacity = cap
            c_kw = float(charge_max) if charge_max is not None else cap
            d_kw = float(discharge_max) if discharge_max is not None else cap
            charge_flow = solph.Flow(nominal_capacity=c_kw)
            discharge_flow = solph.Flow(nominal_capacity=d_kw)

        return solph.components.GenericStorage(
            label=label,
            inputs={bus: charge_flow},
            outputs={bus: discharge_flow},
            nominal_capacity=nominal_capacity,
            min_storage_level=ts.soc_min,
            max_storage_level=ts.soc_max,
            initial_storage_level=ts.soc_initial,
            loss_rate=ts.loss_rate_per_hour,
            inflow_conversion_factor=1.0,
            outflow_conversion_factor=1.0,
        )
