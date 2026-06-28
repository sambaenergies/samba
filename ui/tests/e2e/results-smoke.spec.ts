import { expect, test } from "@playwright/test";

const RUN_ID = "run-complete";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/jobs/*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: RUN_ID,
        status: "completed",
        submitted_at: "2026-01-01T00:00:00Z",
        started_at: "2026-01-01T00:00:10Z",
        completed_at: "2026-01-01T00:00:20Z",
        progress_pct: 100,
        error: null,
        artifacts: [
          "scenario.yaml",
          "metadata.json",
          "kpis.json",
          "sizing.csv",
          "economics.json",
          "dispatch.csv",
          "dispatch.parquet",
          "tariff.parquet",
          "solver.log",
        ],
      }),
    });
  });

  await page.route("**/api/v1/jobs/*/artifacts/kpis.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        kpi_contract_version: "2.1",
        npc: 120000,
        lcoe: 0.12,
        lpsp: 0,
        renewable_fraction: 0.63,
        total_emissions_kg: 1200,
      }),
    });
  });

  await page.route("**/api/v1/jobs/*/artifacts/dispatch.csv", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/csv",
      body: "timestamp,pv_gen,wt_gen,batt_discharge,dg_gen,grid_buy,eload,grid_sell,unmet_load,batt_soc\n2026-01-01 00:00,10,3,2,0,5,18,0,0,60\n2026-01-01 01:00,11,3,1,0,6,19,0,0,59\n",
    });
  });

  await page.route("**/api/v1/jobs/*/artifacts/economics.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        discount_rate_real: 0.05,
        cashflow_annual: [
          {
            year: 0,
            investment: 120000,
            om: 0,
            fuel: 0,
            grid_net: 0,
            replacement: 0,
            salvage: 0,
            total: 120000,
          },
        ],
      }),
    });
  });

  await page.route("**/api/v1/jobs/*/artifacts/sizing.csv", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/csv",
      body: "component,capacity,unit,count,capital_cost\npv,120,kW,1,50000\nbattery,300,kWh,1,70000\n",
    });
  });
});

test("results dashboard smoke", async ({ page }) => {
  await page.goto(`/results/${RUN_ID}`);
  await expect(page.getByText("Results")).toBeVisible();
  await expect(page.getByText("LCOE")).toBeVisible();

  await page.getByRole("button", { name: "Dispatch" }).click();
  await expect(page.getByText("Dispatch")).toBeVisible();

  await page.getByRole("button", { name: "Economics" }).click();
  await expect(page.getByText("Cumulative NPV")).toBeVisible();

  await page.getByRole("button", { name: "Downloads" }).click();
  await expect(page.getByText("scenario.yaml")).toBeVisible();
});
