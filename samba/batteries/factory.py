# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Battery storage factory -- dispatches to the correct builder by chemistry.

Layering rule
-------------
''samba.batteries.factory'' may import from ''samba.compiler.builders.battery''
(Li-ion builder lives there).  The reverse import is forbidden.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import oemof.solph as solph

from samba.batteries.kibam import build_kibam_storage
from samba.compiler.builders.battery import BatteryBuilder

if TYPE_CHECKING:
    from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["build_battery_storage"]


def build_battery_storage(
    scenario: Scenario,
    dc_bus: solph.Bus,
    ac_bus: solph.Bus,
) -> list[solph.network.Node]:
    """Build and return the battery storage node(s) for the given chemistry.

    Dispatches to:

    * ''BatteryBuilder'' (Li-ion, idealized GenericStorage) for
      ''chemistry == "li_ion"''.
    * :func:'~samba.batteries.kibam.build_kibam_storage' (KiBaM LP
      approximation) for ''chemistry == "kibam"''.

    Parameters
    ----------
    scenario:
        Validated scenario; ''scenario.components.battery'' must not be
        ''None''.
    dc_bus:
        DC system bus.
    ac_bus:
        AC system bus (passed through to the Li-ion builder signature;
        unused by the KiBaM path).

    Returns
    -------
    list[solph.network.Node]
        One ''GenericStorage'' node for Li-ion or KiBaM.
    """
    bat = scenario.components.battery
    if bat is None:
        raise ValueError("build_battery_storage called but scenario.components.battery is None")

    match bat.chemistry:
        case "li_ion":
            log.debug("Battery factory: chemistry=li_ion -> BatteryBuilder")
            return BatteryBuilder().build(scenario, dc_bus, ac_bus)
        case "kibam":
            log.debug("Battery factory: chemistry=kibam -> build_kibam_storage")
            return [build_kibam_storage(scenario, dc_bus)]
        case _:  # pragma: no cover
            raise ValueError(f"Unknown battery chemistry: {bat.chemistry!r}")
