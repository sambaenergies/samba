import tseslint from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import vuePlugin from "eslint-plugin-vue";
import vueParser from "vue-eslint-parser";

export default [
  // Generated from JSON Schema (npm run gen:types) — not hand-edited, not linted.
  { ignores: ["src/api/generated/**"] },
  {
    files: ["src/**/*.{ts,vue}"],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tsParser,
        ecmaVersion: "latest",
        sourceType: "module",
        extraFileExtensions: [".vue"],
      },
    },
    plugins: {
      "@typescript-eslint": tseslint,
      vue: vuePlugin,
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "vue/multi-word-component-names": "off",
    },
  },
];
