import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default tseslint.config(
  // Ignore generated and config-only files from type-checked rules
  {
    ignores: [
      "dist/**",
      "coverage/**",
      "*.config.js",
      "*.config.cjs",
      "*.config.ts",
      "postcss.config.cjs",
    ],
  },

  // Base JS recommended for all files
  js.configs.recommended,

  // Strict type-checked rules scoped to src + tests (require type info)
  ...tseslint.configs.strictTypeChecked.map((config) => ({
    ...config,
    files: ["src/**/*.{ts,tsx}", "tests/**/*.{ts,tsx}"],
  })),

  // React plugin rules for all TS/TSX files
  {
    files: ["src/**/*.{ts,tsx}", "tests/**/*.{ts,tsx}"],
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    languageOptions: {
      parserOptions: {
        // typescript-eslint v8 project service — no need to list tsconfig paths manually
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // React hooks
      ...reactHooks.configs.recommended.rules,

      // React Refresh — warn on non-component exports from component files
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],

      // Enforce explicit return types on exported functions (code-standards §4.3)
      "@typescript-eslint/explicit-module-boundary-types": "error",

      // No `any` (code-standards §4.2)
      "@typescript-eslint/no-explicit-any": "error",

      // No non-null assertions outside tests (code-standards §4.2)
      "@typescript-eslint/no-non-null-assertion": "error",
    },
  },

  // Relax non-null assertion rule in test files (spec allows ! in tests)
  {
    files: ["tests/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-non-null-assertion": "off",
    },
  },
);
