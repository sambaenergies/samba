import { defineStore } from "pinia";
import { dump, load } from "js-yaml";

import { validateScenario } from "@/api/validate";
import type { ScenarioDraft, ValidationError } from "@/api/types";

const COMPONENT_ORDER = [
  "pv",
  "wind_turbine",
  "battery",
  "diesel_generator",
  "inverter",
  "grid",
  "ev",
  "heat_pump",
  "thermal_storage",
  "gas_supply",
] as const;

const TOP_LEVEL_KEYS: Array<keyof ScenarioDraft> = [
  "schema_version",
  "project",
  "location",
  "weather",
  "load",
  "components",
  "tariff",
  "constraints",
  "objective",
];

// A complete, schema-valid default scenario (validated against the backend
// `/validate` endpoint — 0 errors, Run enabled). All components are present so
// the editor cards always bind a real object; `enabled` flags select what's on.
// Mirrors examples/base_scenario.yaml (off-grid PV + battery + diesel).
function createDefaultDraft(): ScenarioDraft {
  return {
    schema_version: "2.0",
    project: {
      name: "New Scenario",
      year: 2025,
      lifetime_years: 25,
      discount_rate_nominal: 0.08,
      inflation_rate: 0.03,
      re_incentive_rate: 0.0,
      budget: null,
      currency: "USD",
      capex_year: 0,
    },
    location: {
      latitude: 37.77,
      longitude: -122.42,
      altitude_m: 32.0,
      timezone: "America/Los_Angeles",
    },
    weather: {
      source: "csv",
      csv_path: "content/weather_sf_2019.csv",
    },
    load: {
      source: "hourly_csv",
      csv_path: "content/load_residential_8760.csv",
      scale_factor: 1.0,
    },
    components: {
      pv: {
        enabled: true,
        capacity_kw: null,
        capex_per_kw: 900.0,
        opex_per_kw_yr: 15.0,
        lifetime_years: 25,
        derating_factor: 0.9,
        tilt_deg: 15.0,
        azimuth_deg: 0.0,
        module_type: "monofacial",
      },
      battery: {
        enabled: true,
        capacity_kwh: null,
        power_kw: null,
        chemistry: "li_ion",
        capex_per_kwh: 350.0,
        opex_per_kwh_yr: 5.0,
        lifetime_years: 10,
        soc_min: 0.2,
        soc_max: 1.0,
        soc_initial: 0.5,
        charge_efficiency: 0.95,
        discharge_efficiency: 0.95,
        c_rate_charge: 0.5,
        c_rate_discharge: 0.5,
      },
      inverter: {
        capacity_kw: null,
        capex_per_kw: 200.0,
        opex_per_kw_yr: 5.0,
        lifetime_years: 10,
        efficiency: 0.96,
      },
      diesel_generator: {
        enabled: true,
        capacity_kw: 30.0,
        capex_per_kw: 400.0,
        opex_per_kw_yr: 20.0,
        lifetime_years: 15,
        fuel_price_per_l: 1.2,
        fuel_lhv_kwh_per_l: 9.9,
        slope_l_per_kwh: 0.246,
        intercept_l_per_kw_hr: 0.084,
        min_load_fraction: 0.0,
      },
      wind_turbine: {
        enabled: false,
        count: 1,
        turbine_model: "Enercon_E33_330kW",
        hub_height_m: 50.0,
        capex_per_unit: 450000.0,
        opex_per_unit_yr: 10000.0,
        lifetime_years: 20,
      },
      grid: {
        enabled: false,
        capacity_kw: 100.0,
        export_allowed: false,
        export_capacity_kw: 0.0,
        emission_factor_kg_per_kwh: 0.4,
        capex: 0.0,
        opex_yr: 0.0,
      },
      ev: {
        enabled: false,
        capacity_kwh: 60.0,
        max_charge_kw: 7.0,
        max_discharge_kw: 0.0,
        capex: 0.0,
        opex_per_year: 0.0,
        lifetime_years: 10,
        v2g_enabled: false,
      },
      heat_pump: {
        enabled: false,
        mode: "both",
        sizing: "catalog_auto",
        cop_source: "catalog",
        capex: 8000.0,
        opex_per_year: 160.0,
        lifetime_years: 15,
      },
      thermal_storage: {
        enabled: false,
        capacity_kwh_th: null,
        capex_per_kwh_th: 30.0,
        opex_per_year: 0.0,
        lifetime_years: 20,
        loss_rate_per_hour: 0.002,
        include_cooling_storage: false,
      },
      gas_supply: {
        enabled: false,
        boiler_efficiency: 0.9,
        max_output_kw_th: 50.0,
        capex: 3000.0,
        opex_per_year: 50.0,
        lifetime_years: 20,
      },
    },
    tariff: {
      buy: { type: "flat", rate_per_kwh: 0.0 },
    },
    constraints: {
      min_renewable_fraction: 0.0,
      max_annual_diesel_l: null,
      max_battery_cycles_yr: null,
      max_lpsp: 0.05,
      force_grid_disconnect: false,
    },
    objective: {
      type: "cost",
    },
  };
}

function cloneDraft(draft: ScenarioDraft): ScenarioDraft {
  return JSON.parse(JSON.stringify(draft)) as ScenarioDraft;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Recursively overlay `source` onto `target` (arrays/primitives replace). */
function deepMerge(
  target: Record<string, unknown>,
  source: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...target };
  for (const [key, value] of Object.entries(source)) {
    out[key] = isPlainObject(value) && isPlainObject(out[key])
      ? deepMerge(out[key] as Record<string, unknown>, value)
      : value;
  }
  return out;
}

/**
 * Merge an imported scenario onto a full default draft so omitted fields keep
 * sensible defaults. Components the YAML omits (or sets null) are kept as
 * bindable default objects turned **off**, preserving the editor's
 * "every component present" invariant without changing the imported scenario's
 * meaning.
 */
function mergeImportedDraft(imported: Record<string, unknown>): ScenarioDraft {
  const merged = deepMerge(
    createDefaultDraft() as unknown as Record<string, unknown>,
    imported,
  ) as unknown as ScenarioDraft;

  const importedComps = isPlainObject(imported.components) ? imported.components : {};
  const defaults = createDefaultDraft().components as unknown as Record<string, Record<string, unknown>>;
  const comps = merged.components as unknown as Record<string, Record<string, unknown> | null>;
  for (const name of COMPONENT_ORDER) {
    const provided = name in importedComps && importedComps[name] != null;
    if (!provided) {
      const fallback = { ...defaults[name] };
      if ("enabled" in fallback) {
        fallback.enabled = false;
      }
      comps[name] = fallback;
    }
  }
  return merged;
}

function normalizeValidationErrors(errors: unknown): ValidationError[] {
  if (!Array.isArray(errors)) {
    return [];
  }

  const normalized: ValidationError[] = [];
  for (const item of errors) {
    if (typeof item === "string") {
      // Backend emits "<dotted.loc.path>: <message>" (see samba/scenario/loader.py).
      // Recover the path so section badges + inline field errors route correctly;
      // a prefix containing whitespace is a plain message (no path).
      const sep = item.indexOf(": ");
      const prefix = sep > 0 ? item.slice(0, sep) : "";
      if (prefix && !/\s/.test(prefix)) {
        normalized.push({ path: prefix.split("."), message: item.slice(sep + 2), severity: "error" });
      } else {
        normalized.push({ path: [], message: item, severity: "error" });
      }
      continue;
    }

    if (typeof item === "object" && item !== null) {
      const candidate = item as {
        path?: unknown;
        loc?: unknown;
        message?: unknown;
        msg?: unknown;
        severity?: unknown;
      };

      const path = Array.isArray(candidate.path)
        ? candidate.path.map(String)
        : Array.isArray(candidate.loc)
          ? candidate.loc.map(String)
          : [];
      const message =
        typeof candidate.message === "string"
          ? candidate.message
          : typeof candidate.msg === "string"
            ? candidate.msg
            : "Validation error";
      const severity = candidate.severity === "warning" ? "warning" : "error";

      normalized.push({ path, message, severity });
    }
  }

  return normalized;
}

export const useScenarioStore = defineStore("scenario", {
  state: () => ({
    draft: createDefaultDraft() as ScenarioDraft,
    baseline: createDefaultDraft() as ScenarioDraft,
    isDirty: false,
    validationErrors: [] as ValidationError[],
    validationPending: false,
    lastSavedAt: null as number | null,
    validationTimer: null as ReturnType<typeof setTimeout> | null,
  }),
  getters: {
    errorCount(state): number {
      return state.validationErrors.filter((error) => error.severity === "error").length;
    },
    warningCount(state): number {
      return state.validationErrors.filter((error) => error.severity === "warning").length;
    },
    componentOrder(): readonly string[] {
      return COMPONENT_ORDER;
    },
  },
  actions: {
    touchDraft() {
      this.updateDirtyFlag();
      this.scheduleValidate();
    },
    updateDirtyFlag() {
      this.isDirty = JSON.stringify(this.draft) !== JSON.stringify(this.baseline);
    },
    scheduleValidate() {
      if (this.validationTimer) {
        clearTimeout(this.validationTimer);
      }
      this.validationTimer = setTimeout(() => {
        void this.validateNow();
      }, 500);
    },
    setField(path: string[], value: unknown) {
      if (!path.length) {
        return;
      }

      let cursor: Record<string, unknown> = this.draft as unknown as Record<string, unknown>;
      for (let index = 0; index < path.length - 1; index += 1) {
        const key = path[index];
        const next = cursor[key];
        if (typeof next !== "object" || next === null) {
          cursor[key] = {};
        }
        cursor = cursor[key] as Record<string, unknown>;
      }

      cursor[path[path.length - 1]] = value;
      this.updateDirtyFlag();
      this.scheduleValidate();
    },
    async importYaml(text: string) {
      try {
        const parsed = load(text);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          this.validationErrors = [{ path: [], message: "YAML must be a scenario object.", severity: "error" }];
          return;
        }

        const asRecord = parsed as Record<string, unknown>;
        const unknownKeys = Object.keys(asRecord).filter(
          (key) => !TOP_LEVEL_KEYS.includes(key as keyof ScenarioDraft),
        );

        const merged = mergeImportedDraft(asRecord);

        this.draft = merged;
        this.baseline = cloneDraft(merged);
        this.isDirty = false;
        this.validationErrors = unknownKeys.map((key) => ({
          path: [key],
          message: `Unknown top-level key: ${key}`,
          severity: "warning" as const,
        }));
        this.lastSavedAt = Date.now();
        await this.validateNow();
      } catch (error) {
        this.validationErrors = [
          {
            path: [],
            message: error instanceof Error ? `YAML import failed: ${error.message}` : "YAML import failed.",
            severity: "error",
          },
        ];
      }
    },
    exportYaml(): string {
      this.lastSavedAt = Date.now();
      return dump(this.draft, { indent: 2, lineWidth: 120 });
    },
    resetToDefaults() {
      this.draft = createDefaultDraft();
      this.baseline = cloneDraft(this.draft);
      this.validationErrors = [];
      this.isDirty = false;
      this.lastSavedAt = Date.now();
      this.scheduleValidate();
    },
    async validateNow() {
      this.validationPending = true;
      try {
        const response = await validateScenario(this.draft);
        const normalized = normalizeValidationErrors((response as { errors?: unknown }).errors);
        this.validationErrors = normalized;
      } catch (error) {
        this.validationErrors = [
          {
            path: [],
            message: error instanceof Error ? error.message : "Validation request failed.",
            severity: "error",
          },
        ];
      } finally {
        this.validationPending = false;
      }
    },
    errorAt(path: string[]): ValidationError | null {
      const joined = path.join(".");
      return (
        this.validationErrors.find((error) => {
          const target = error.path.join(".");
          return target === joined || target.startsWith(`${joined}.`);
        }) ?? null
      );
    },
  },
});
