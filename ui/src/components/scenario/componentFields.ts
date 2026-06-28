// Curated, schema-accurate field descriptors per component, used by
// ComponentCard to render the editor. Field keys match the generated Scenario
// component types (src/api/generated/scenario.ts); adding a backend field here
// is a one-line, type-checked change. Not every schema field is exposed — the
// default draft carries valid values for the rest.

export type FieldKind = "number" | "text" | "select" | "bool";

export interface FieldSpec {
  key: string;
  label: string;
  kind: FieldKind;
  step?: number;
  options?: readonly string[];
  placeholder?: string;
}

export const COMPONENT_FIELDS: Record<string, readonly FieldSpec[]> = {
  pv: [
    { key: "capacity_kw", label: "Capacity kW (blank = auto)", kind: "number" },
    { key: "capex_per_kw", label: "Capex /kW", kind: "number" },
    { key: "opex_per_kw_yr", label: "Opex /kW·yr", kind: "number" },
    { key: "lifetime_years", label: "Lifetime (yr)", kind: "number" },
    { key: "tilt_deg", label: "Tilt °", kind: "number" },
    { key: "azimuth_deg", label: "Azimuth °", kind: "number" },
    { key: "derating_factor", label: "Derating", kind: "number", step: 0.01 },
    { key: "module_type", label: "Module", kind: "select", options: ["monofacial", "bifacial"] },
  ],
  wind_turbine: [
    { key: "count", label: "Count", kind: "number" },
    { key: "turbine_model", label: "Turbine model", kind: "text" },
    { key: "hub_height_m", label: "Hub height (m)", kind: "number" },
    { key: "capex_per_unit", label: "Capex /unit", kind: "number" },
    { key: "opex_per_unit_yr", label: "Opex /unit·yr", kind: "number" },
    { key: "lifetime_years", label: "Lifetime (yr)", kind: "number" },
  ],
  battery: [
    { key: "capacity_kwh", label: "Capacity kWh (blank = auto)", kind: "number" },
    { key: "power_kw", label: "Power kW (blank = derived)", kind: "number" },
    { key: "chemistry", label: "Chemistry", kind: "select", options: ["li_ion", "kibam"] },
    { key: "capex_per_kwh", label: "Capex /kWh", kind: "number" },
    { key: "opex_per_kwh_yr", label: "Opex /kWh·yr", kind: "number" },
    { key: "lifetime_years", label: "Lifetime (yr)", kind: "number" },
    { key: "soc_min", label: "SoC min", kind: "number", step: 0.01 },
    { key: "soc_max", label: "SoC max", kind: "number", step: 0.01 },
    { key: "charge_efficiency", label: "Charge eff.", kind: "number", step: 0.01 },
    { key: "discharge_efficiency", label: "Discharge eff.", kind: "number", step: 0.01 },
  ],
  diesel_generator: [
    { key: "capacity_kw", label: "Capacity kW", kind: "number" },
    { key: "capex_per_kw", label: "Capex /kW", kind: "number" },
    { key: "opex_per_kw_yr", label: "Opex /kW·yr", kind: "number" },
    { key: "lifetime_years", label: "Lifetime (yr)", kind: "number" },
    { key: "fuel_price_per_l", label: "Fuel price /L", kind: "number", step: 0.01 },
    { key: "min_load_fraction", label: "Min load frac.", kind: "number", step: 0.01 },
  ],
  inverter: [
    { key: "capacity_kw", label: "Capacity kW (blank = auto)", kind: "number" },
    { key: "capex_per_kw", label: "Capex /kW", kind: "number" },
    { key: "opex_per_kw_yr", label: "Opex /kW·yr", kind: "number" },
    { key: "lifetime_years", label: "Lifetime (yr)", kind: "number" },
    { key: "efficiency", label: "Efficiency", kind: "number", step: 0.01 },
  ],
  grid: [
    { key: "capacity_kw", label: "Import limit kW", kind: "number" },
    { key: "export_allowed", label: "Export allowed", kind: "bool" },
    { key: "export_capacity_kw", label: "Export limit kW", kind: "number" },
    { key: "emission_factor_kg_per_kwh", label: "CO₂ kg/kWh", kind: "number", step: 0.001 },
    { key: "capex", label: "Connection capex", kind: "number" },
    { key: "opex_yr", label: "Standing charge /yr", kind: "number" },
  ],
  ev: [
    { key: "capacity_kwh", label: "Battery kWh", kind: "number" },
    { key: "max_charge_kw", label: "Max charge kW", kind: "number" },
    { key: "max_discharge_kw", label: "Max discharge kW (V2G)", kind: "number" },
    { key: "v2g_enabled", label: "V2G enabled", kind: "bool" },
    { key: "capex", label: "Capex", kind: "number" },
    { key: "lifetime_years", label: "Lifetime (yr)", kind: "number" },
  ],
  heat_pump: [
    { key: "mode", label: "Mode", kind: "select", options: ["heating_only", "cooling_only", "both"] },
    { key: "sizing", label: "Sizing", kind: "select", options: ["catalog_auto", "fixed"] },
    { key: "cop_source", label: "COP source", kind: "select", options: ["catalog", "fixed", "dataset"] },
    { key: "capex", label: "Capex", kind: "number" },
    { key: "opex_per_year", label: "Opex /yr", kind: "number" },
    { key: "lifetime_years", label: "Lifetime (yr)", kind: "number" },
  ],
  thermal_storage: [
    { key: "capacity_kwh_th", label: "Capacity kWh_th (blank = auto)", kind: "number" },
    { key: "capex_per_kwh_th", label: "Capex /kWh_th", kind: "number" },
    { key: "loss_rate_per_hour", label: "Loss rate /h", kind: "number", step: 0.001 },
    { key: "include_cooling_storage", label: "Cooling storage", kind: "bool" },
    { key: "opex_per_year", label: "Opex /yr", kind: "number" },
    { key: "lifetime_years", label: "Lifetime (yr)", kind: "number" },
  ],
  gas_supply: [
    { key: "boiler_efficiency", label: "Boiler efficiency", kind: "number", step: 0.01 },
    { key: "max_output_kw_th", label: "Max output kW_th", kind: "number" },
    { key: "capex", label: "Capex", kind: "number" },
    { key: "opex_per_year", label: "Opex /yr", kind: "number" },
    { key: "lifetime_years", label: "Lifetime (yr)", kind: "number" },
  ],
};
