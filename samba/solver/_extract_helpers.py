# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Shared helper functions for solver dispatch extraction."""

from __future__ import annotations

from typing import Any

import pandas as pd

__all__ = [
    "_col",
    "_get_battery_capacity",
    "_invest_flow_capacity",
    "_invest_or_fixed_flow",
    "_node_col",
]


def _col(
    src: Any,
    tgt: Any,
    flow_df: pd.DataFrame,
    timeindex: pd.DatetimeIndex,
) -> pd.Series:
    """Return the flow series for ``(src -> tgt)``; zero if absent.

    Uses ``iloc`` via ``columns.get_loc()`` instead of ``df[key]`` to avoid
    pandas treating a tuple key as a multi-column selection on non-MultiIndex
    DataFrames (``is_list_like`` check in ``DataFrame.__getitem__``).
    """
    if src is None or tgt is None:
        return pd.Series(0.0, index=timeindex, dtype=float)
    key = (src, tgt)
    if key in flow_df.columns:
        pos = flow_df.columns.get_loc(key)
        return flow_df.iloc[:, pos].astype(float)
    return pd.Series(0.0, index=timeindex, dtype=float)


def _node_col(df: pd.DataFrame, node: Any) -> pd.Series | None:
    """Return the column Series for a plain node key using ``get_loc``.

    Avoids the same ``is_list_like`` pandas pitfall for non-tuple node
    objects (e.g. GenericStorage nodes in ``soc_df`` / ``invest_df``).
    Returns ``None`` if the key is absent.
    """
    if node is None or node not in df.columns:
        return None
    pos = df.columns.get_loc(node)
    return df.iloc[:, pos]


def _get_battery_capacity(batt_node: Any, invest_df: pd.DataFrame | None) -> float:
    """Return battery energy capacity (kWh) from investment results or node attribute."""
    if batt_node is None:
        return 0.0
    if invest_df is not None and not invest_df.empty and batt_node in invest_df.columns:
        pos = invest_df.columns.get_loc(batt_node)
        val = float(invest_df.iloc[0, pos])
        if val > 0:
            return val
    cap = getattr(batt_node, "nominal_storage_capacity", None)
    if cap is not None:
        return float(cap)
    return 0.0


def _invest_flow_capacity(src: Any, tgt: Any, invest_df: pd.DataFrame | None) -> float | None:
    """Return investment capacity for an ``(src, tgt)`` flow, or ``None`` if unavailable."""
    if src is None or tgt is None or invest_df is None or invest_df.empty:
        return None
    col = (src, tgt)
    if col in invest_df.columns:
        pos = invest_df.columns.get_loc(col)
        val = float(invest_df.iloc[0, pos])
        return val if val > 0 else None
    return None


def _invest_or_fixed_flow(
    src: Any,
    tgt: Any,
    direction: str,
    invest_df: pd.DataFrame | None,
    node: Any,
) -> float | None:
    """Return investment capacity or fixed ``nominal_capacity`` from node flow."""
    cap = _invest_flow_capacity(src, tgt, invest_df)
    if cap is not None:
        return cap
    try:
        if direction == "outputs" and hasattr(node, "outputs"):
            for bus, flow in node.outputs.items():
                if bus is tgt:
                    nc = getattr(flow, "nominal_capacity", None)
                    if nc is not None and not isinstance(nc, type):
                        return float(nc)
        elif direction == "inputs" and hasattr(node, "inputs"):
            for bus, flow in node.inputs.items():
                if bus is src:
                    nc = getattr(flow, "nominal_capacity", None)
                    if nc is not None and not isinstance(nc, type):
                        return float(nc)
    except Exception:  # noqa: BLE001
        pass
    return None
