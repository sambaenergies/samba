import type { CashflowRow } from "@/api/types";

/**
 * Map `economics.json` `cashflow_annual` rows to {@link CashflowRow}. The backend
 * fields are `investment / om / fuel / grid_net / replacement / salvage / total`;
 * `cumulative_npv` is not stored, so we compute it here as the running discounted
 * sum of `total` using `discount_rate_real` (its final value equals the NPC).
 */
export function extractCashflows(economics: object): CashflowRow[] {
  const source = economics as {
    cashflow_annual?: Array<Record<string, unknown>>;
    discount_rate_real?: unknown;
  };
  if (!Array.isArray(source.cashflow_annual)) {
    return [];
  }

  const rate = Number(source.discount_rate_real ?? 0);
  let cumulative = 0;

  return source.cashflow_annual.map((row, index) => {
    const year = Number(row.year ?? index);
    const total = Number(row.total ?? 0);
    cumulative += rate > -1 ? total / Math.pow(1 + rate, year) : total;
    return {
      year,
      investment: Number(row.investment ?? 0),
      om: Number(row.om ?? 0),
      fuel: Number(row.fuel ?? 0),
      grid_net: Number(row.grid_net ?? 0),
      replacement: Number(row.replacement ?? 0),
      salvage: Number(row.salvage ?? 0),
      total,
      cumulative_npv: cumulative,
    };
  });
}
