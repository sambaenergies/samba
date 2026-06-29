// Generate TypeScript types from the vendored contract.
//
// Source: ui/contract/ (vendored from the backend export by `just contract-sync`).
// Two generators, by role:
//   - openapi.ts            <- ui/contract/openapi.json via openapi-typescript.
//                              The full HTTP contract: `paths` (route-aware) and
//                              `components` (every request/response envelope). The
//                              openapi-fetch client and the api/* envelope types
//                              are built from this.
//   - <artifact>.ts         <- ui/contract/<artifact>.schema.json via
//                              json-schema-to-typescript. ONLY the downloadable
//                              result artifacts (parsed client-side from files in
//                              stores/results.ts, never HTTP JSON bodies).
//
// Reading from ui/contract/ keeps the UI build self-contained (no reach into the
// Python tree). Output: src/api/generated/*.ts (committed, drift-gated via
// `git diff --exit-code`). Run with: npm run gen:types (or backend `just contract`).

import { compileFromFile } from "json-schema-to-typescript";
import openapiTS, { astToString } from "openapi-typescript";
import { readdirSync, rmSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const contractDir = resolve(here, "..", "contract");
const outDir = resolve(here, "..", "src", "api", "generated");

// Downloadable result artifacts only -- envelope shapes (health/validate/job/
// job_submit/error) come from openapi.ts, not a companion file.
const ARTIFACT_SCHEMAS = new Set(["scenario", "kpis", "economics", "sizing", "dispatch"]);

const banner =
  "/* eslint-disable */\n/**\n * AUTO-GENERATED from ui/contract by `npm run gen:types`. DO NOT EDIT.\n * Source of truth: backend Pydantic models (see scripts/export_schemas.py).\n */";

mkdirSync(outDir, { recursive: true });

// Clear stale generated files so a removed/renamed schema cannot leave an orphan.
for (const f of readdirSync(outDir).filter((f) => f.endsWith(".ts"))) {
  rmSync(join(outDir, f));
}

// 1. Route-aware HTTP contract from OpenAPI.
const openapiDoc = JSON.parse(readFileSync(join(contractDir, "openapi.json"), "utf-8"));
const ast = await openapiTS(openapiDoc);
writeFileSync(join(outDir, "openapi.ts"), `${banner}\n\n${astToString(ast)}`, "utf-8");
console.log("generated src/api/generated/openapi.ts");

// 2. Companion artifact types from JSON Schema.
const options = {
  additionalProperties: false, // schemas use extra="forbid"; keep types strict
  bannerComment: banner,
  style: { singleQuote: false, semi: true },
};

const files = readdirSync(contractDir)
  .filter((f) => f.endsWith(".schema.json"))
  .filter((f) => ARTIFACT_SCHEMAS.has(f.replace(/\.schema\.json$/, "")))
  .sort();

for (const file of files) {
  const name = file.replace(/\.schema\.json$/, "");
  const ts = await compileFromFile(join(contractDir, file), options);
  writeFileSync(join(outDir, `${name}.ts`), ts, "utf-8");
  console.log(`generated src/api/generated/${name}.ts`);
}
