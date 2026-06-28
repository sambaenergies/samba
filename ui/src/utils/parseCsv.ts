import Papa from "papaparse";

import type { DispatchData, MonthlyRow } from "@/api/types";

export function parseDispatchCsv(text: string): DispatchData {
  const parsed = Papa.parse<Record<string, string | number>>(text, {
    header: true,
    dynamicTyping: true,
    skipEmptyLines: true,
  });

  const timestamps: string[] = [];
  const series: Record<string, number[]> = {};

  for (const row of parsed.data) {
    const entries = Object.entries(row);
    if (!entries.length) {
      continue;
    }

    const [timestampKey, timestampValue] = entries[0];
    timestamps.push(String(timestampValue ?? row.timestamp ?? row[timestampKey] ?? ""));

    for (const [key, value] of entries.slice(1)) {
      if (!series[key]) {
        series[key] = [];
      }
      const numeric = typeof value === "number" ? value : Number(value ?? 0);
      series[key].push(Number.isFinite(numeric) ? numeric : 0);
    }
  }

  return { timestamps, series };
}

function monthFromTimestamp(timestamp: string): number {
  const parsed = new Date(timestamp);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.getMonth() + 1;
  }

  const split = timestamp.split(/[-/ ]/);
  const month = Number(split[1] ?? 1);
  return Number.isFinite(month) && month >= 1 && month <= 12 ? month : 1;
}

export function aggregateMonthlyFromDispatch(data: DispatchData): MonthlyRow[] {
  const rows: MonthlyRow[] = Array.from({ length: 12 }, (_v, idx) => ({
    month: idx + 1,
    pv_kwh: 0,
    wind_kwh: 0,
    battery_discharge_kwh: 0,
    diesel_kwh: 0,
    grid_import_kwh: 0,
    load_kwh: 0,
    grid_export_kwh: 0,
    unmet_kwh: 0,
  }));

  data.timestamps.forEach((timestamp, index) => {
    const month = monthFromTimestamp(timestamp);
    const row = rows[month - 1];

    row.pv_kwh += data.series.pv_gen?.[index] ?? 0;
    row.wind_kwh += data.series.wt_gen?.[index] ?? 0;
    row.battery_discharge_kwh += data.series.batt_discharge?.[index] ?? 0;
    row.diesel_kwh += data.series.dg_gen?.[index] ?? 0;
    row.grid_import_kwh += data.series.grid_buy?.[index] ?? 0;
    row.load_kwh += data.series.eload?.[index] ?? 0;
    row.grid_export_kwh += data.series.grid_sell?.[index] ?? 0;
    row.unmet_kwh += data.series.unmet_load?.[index] ?? 0;
  });

  return rows;
}
