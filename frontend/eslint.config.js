import js from "@eslint/js";
import tseslint from "typescript-eslint";
import solid from "eslint-plugin-solid/configs/typescript";
import globals from "globals";

export default tseslint.config(
  // Base JS rules
  js.configs.recommended,

  // TypeScript rules
  ...tseslint.configs.recommended,

  // SolidJS + TypeScript rules
  {
    ...solid,
    languageOptions: {
      ...solid.languageOptions,
      globals: globals.browser,
      parserOptions: {
        project: "./tsconfig.json",
      },
    },
  },

  // Project-wide overrides
  {
    rules: {
      // Allow unused vars prefixed with _ (common for intentionally unused params)
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },

  // Ignore build output
  {
    ignores: ["dist/**", "node_modules/**"],
  },
);
