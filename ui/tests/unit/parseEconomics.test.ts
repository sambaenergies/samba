import { describe, expect, it } from "vitest";

import { extractCashflows } from "@/utils/parseEconomics";

describe("extractCashflows", () => {
  it("maps economics cashflow_annual rows to the UI schema", () => {
    const payload = {
      discount_rate_real: 0.05,
      cashflow_annual: [
        { year: 0, investment: 100, om: 0, fuel: 0, grid_net: 0, replacement: 0, salvage: 0, total: 100 },
        { year: 1, investment: 0, om: 10, fuel: 5, grid_net: 2, replacement: 0, salvage: 0, total: 17 },
      ],
    };

    const rows = extractCashflows(payload);
    expect(rows).toHaveLength(2);
    expect(rows[0].investment).toBe(100);
    expect(rows[0].om).toBe(0);
    expect(rows[1].om).toBe(10);
    // cumulative_npv is the running discounted sum of `total`.
    expect(rows[0].cumulative_npv).toBeCloseTo(100, 6);
    expect(rows[1].cumulative_npv).toBeCloseTo(100 + 17 / 1.05, 6);
  });

  it("returns empty for missing cashflow array", () => {
    const rows = extractCashflows({});
    expect(rows).toEqual([]);
  });
});
