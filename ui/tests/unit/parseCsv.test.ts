import { describe, expect, it } from "vitest";

import { aggregateMonthlyFromDispatch, parseDispatchCsv } from "@/utils/parseCsv";

describe("parseDispatchCsv", () => {
  it("parses dispatch csv rows and series", () => {
    const csv = [
      "timestamp,pv_gen,dg_gen,eload,grid_buy",
      "2026-01-01 00:00,1,0,2,1",
      "2026-01-01 01:00,2,0,3,1",
    ].join("\n");

    const parsed = parseDispatchCsv(csv);
    expect(parsed.timestamps).toHaveLength(2);
    expect(parsed.series.pv_gen).toEqual([1, 2]);
    expect(parsed.series.eload).toEqual([2, 3]);
  });

  it("aggregates monthly totals", () => {
    const data = {
      timestamps: ["2026-01-01 00:00", "2026-02-01 00:00"],
      series: {
        pv_gen: [1, 2],
        wt_gen: [2, 3],
        batt_discharge: [0.5, 0.25],
        dg_gen: [0, 1],
        grid_buy: [1, 1],
        eload: [4, 5],
        grid_sell: [0, 0.5],
        unmet_load: [0, 0],
      },
    };

    const monthly = aggregateMonthlyFromDispatch(data);
    expect(monthly[0].pv_kwh).toBe(1);
    expect(monthly[1].pv_kwh).toBe(2);
    expect(monthly[1].grid_export_kwh).toBe(0.5);
    expect(monthly[2].load_kwh).toBe(0);
  });
});
