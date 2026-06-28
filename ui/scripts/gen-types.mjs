// Generate TypeScript types from the backend-exported JSON Schemas.
//
// Source of truth: ../schemas/*.schema.json (emitted from Pydantic by
// `just schemas`). Output: src/api/generated/*.ts (committed). A drift gate
// (`npm run gen:types` + `git diff --exit-code`) keeps the two in sync, so the
// UI types can never silently diverge from the backend contracts.
//
// Run with: npm run gen:types

import { compileFromFile } from "json-schema-to-typescript";
import { readdirSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const schemasDir = resolve(here, "..", "..", "schemas");
const outDir = resolve(here, "..", "src", "api", "generated");

const options = {
  additionalProperties: false, // schemas use extra="forbid"; keep types strict
  bannerComment:
    "/* eslint-disable */\n/**\n * AUTO-GENERATED from ../../../schemas by `npm run gen:types`. DO NOT EDIT.\n * Source of truth: backend Pydantic models (see scripts/export_schemas.py).\n */",
  style: { singleQuote: false, semi: true },
};

mkdirSync(outDir, { recursive: true });

const files = readdirSync(schemasDir)
  .filter((f) => f.endsWith(".schema.json"))
  .sort();

for (const file of files) {
  const name = file.replace(/\.schema\.json$/, "");
  const ts = await compileFromFile(join(schemasDir, file), options);
  writeFileSync(join(outDir, `${name}.ts`), ts, "utf-8");
  console.log(`generated src/api/generated/${name}.ts`);
}
