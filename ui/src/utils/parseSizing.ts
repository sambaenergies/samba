import Papa from "papaparse";

import type { SizingRow } from "@/api/types";

export function parseSizingCsv(text: string): SizingRow[] {
  const parsed = Papa.parse<Record<string, string | number>>(text, {
    header: true,
    dynamicTyping: true,
    skipEmptyLines: true,
  });

  return parsed.data.map((row) => ({
    component: String(row.component ?? row.name ?? "component"),
    capacity: Number(row.capacity ?? row.value ?? 0),
    unit: String(row.unit ?? ""),
    count: Number(row.count ?? 1),
    capital_cost: Number(row.capital_cost ?? row.capex ?? row.cost ?? 0),
  }));
}
