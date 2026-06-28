import { expect, test } from "@playwright/test";

const RUN_ID = "run-dispatch";

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
        artifacts: ["kpis.json", "dispatch.csv", "economics.json", "sizing.csv"],
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
      body: "timestamp,pv_gen,wt_gen,batt_discharge,dg_gen,grid_buy,eload,grid_sell,unmet_load,batt_soc\n2026-01-01 00:00,10,3,2,0,5,18,0,0,60\n2026-01-01 01:00,12,3,1,0,4,19,0,0,58\n2026-01-01 02:00,13,2,1,0,6,21,0,0,57\n",
    });
  });

  await page.route("**/api/v1/jobs/*/artifacts/economics.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ cashflow_annual: [] }),
    });
  });

  await page.route("**/api/v1/jobs/*/artifacts/sizing.csv", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/csv",
      body: "component,capacity,unit,count,capital_cost\npv,120,kW,1,50000\n",
    });
  });
});

test("dispatch zoom controls", async ({ page }) => {
  await page.goto(`/results/${RUN_ID}`);
  await page.getByRole("button", { name: "Dispatch" }).click();

  await expect(page.getByRole("button", { name: "Full Year" })).toBeVisible();
  await page.getByRole("button", { name: "Full Year" }).click();
  await page.getByRole("button", { name: "Week 1" }).click();

  await expect(page.locator("canvas").first()).toBeVisible();
});
