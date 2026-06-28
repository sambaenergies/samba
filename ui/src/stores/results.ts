import { defineStore } from "pinia";

import { fetchArtifact } from "@/api/artifacts";
import { getJob } from "@/api/jobs";
import type { CashflowRow, DispatchData, JobRecord, KpiSummary, MonthlyRow, SizingRow } from "@/api/types";
import { aggregateMonthlyFromDispatch, parseDispatchCsv } from "@/utils/parseCsv";
import { extractCashflows } from "@/utils/parseEconomics";
import { parseSizingCsv } from "@/utils/parseSizing";

const ARTIFACTS = [
  "scenario.yaml",
  "metadata.json",
  "kpis.json",
  "sizing.csv",
  "economics.json",
  "dispatch.csv",
  "dispatch.parquet",
  "tariff.parquet",
  "solver.log",
] as const;

export const useResultsStore = defineStore("results", {
  state: () => ({
    activeRunId: null as string | null,
    job: null as JobRecord | null,
    pollingActive: false,
    kpis: null as KpiSummary | null,
    dispatch: null as DispatchData | null,
    cashflows: null as CashflowRow[] | null,
    monthlySummary: null as MonthlyRow[] | null,
    sizing: null as SizingRow[] | null,
    availableArtifacts: [] as string[],
    loadingArtifacts: false,
    pollingTimer: null as ReturnType<typeof setInterval> | null,
  }),
  actions: {
    resetData() {
      this.kpis = null;
      this.dispatch = null;
      this.cashflows = null;
      this.monthlySummary = null;
      this.sizing = null;
      this.availableArtifacts = [];
    },
    async loadResult(runId: string) {
      this.activeRunId = runId;
      this.resetData();
      this.job = await getJob(runId);
      if (this.job.status === "completed") {
        await this.fetchArtifacts();
        return;
      }
      if (this.job.status === "failed") {
        return;
      }
      this.startPolling();
    },
    startPolling() {
      if (!this.activeRunId || this.pollingActive) {
        return;
      }
      this.pollingActive = true;
      this.pollingTimer = setInterval(async () => {
        if (!this.activeRunId) {
          return;
        }
        this.job = await getJob(this.activeRunId);
        if (this.job.status === "completed") {
          this.stopPolling();
          await this.fetchArtifacts();
        }
        if (this.job.status === "failed") {
          this.stopPolling();
        }
      }, 2_000);
    },
    stopPolling() {
      this.pollingActive = false;
      if (this.pollingTimer) {
        clearInterval(this.pollingTimer);
        this.pollingTimer = null;
      }
    },
    async fetchArtifacts() {
      if (!this.activeRunId) {
        return;
      }
      this.loadingArtifacts = true;
      try {
        const runId = this.activeRunId;

        const kpiBlob = await fetchArtifact(runId, "kpis.json");
        this.kpis = JSON.parse(await kpiBlob.text()) as KpiSummary;

        const dispatchBlob = await fetchArtifact(runId, "dispatch.csv");
        this.dispatch = parseDispatchCsv(await dispatchBlob.text());
        this.monthlySummary = aggregateMonthlyFromDispatch(this.dispatch);

        const economicsBlob = await fetchArtifact(runId, "economics.json");
        this.cashflows = extractCashflows(JSON.parse(await economicsBlob.text()) as object);

        const sizingBlob = await fetchArtifact(runId, "sizing.csv");
        this.sizing = parseSizingCsv(await sizingBlob.text());

        this.availableArtifacts = ARTIFACTS.filter((name) =>
          this.job?.artifacts?.includes(name) ?? false,
        );
      } finally {
        this.loadingArtifacts = false;
      }
    },
  },
});
