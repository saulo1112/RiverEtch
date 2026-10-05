// @ts-check
// Single ESLint flat config for every JS/TS file in the monorepo.
import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import prettier from "eslint-config-prettier/flat";
import jsdoc from "eslint-plugin-jsdoc";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  globalIgnores([
    "**/node_modules/",
    "**/dist/",
    "**/coverage/",
    "contracts/artifacts/",
    "contracts/cache/",
    "contracts/types/",
    "contracts/build/",
    "contracts/src/generated/",
    "pipeline/",
  ]),

  // Baseline: ESLint recommended + typescript-eslint strict, type-aware rules.
  js.configs.recommended,
  tseslint.configs.strictTypeChecked,
  tseslint.configs.stylisticTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        // Resolves the closest tsconfig.json for each file, so every workspace keeps its own.
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
    },
  },

  // Plain JS files (tooling configs) are not part of any tsconfig: lint them without type info.
  {
    files: ["**/*.{js,mjs,cjs}"],
    extends: [tseslint.configs.disableTypeChecked],
    languageOptions: { globals: globals.node },
  },

  // Documentation standard: TSDoc comments on every exported function, component and class.
  {
    files: ["**/*.{ts,tsx}"],
    extends: [jsdoc.configs["flat/recommended-typescript-error"]],
    rules: {
      "jsdoc/require-jsdoc": [
        "error",
        {
          publicOnly: true,
          require: {
            FunctionDeclaration: true,
            FunctionExpression: true,
            ArrowFunctionExpression: true,
            ClassDeclaration: true,
            MethodDefinition: true,
          },
        },
      ],
      "jsdoc/require-description": "error",
      // Destructured props are documented on their props type instead of as `@param root0`.
      "jsdoc/require-param": ["error", { checkDestructuredRoots: false }],
      // TSDoc syntax: `@param name - description`.
      "jsdoc/require-hyphen-before-param-description": ["error", "always"],
      // One blank line between the description and the first tag.
      "jsdoc/tag-lines": ["error", "any", { startLines: 1 }],
      "jsdoc/check-tag-names": [
        "error",
        {
          definedTags: [
            "remarks",
            "typeParam",
            "defaultValue",
            "privateRemarks",
            "packageDocumentation",
          ],
        },
      ],
    },
  },

  // Must stay last: turns off every rule that would fight with Prettier's formatting.
  prettier,
]);
