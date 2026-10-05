// Pre-commit checks, run by Husky on staged files only (fast: no tests, no full-repo scans).
// Formatting problems are fixed and re-staged automatically; anything that cannot be fixed
// (missing TSDoc/NatSpec/docstrings, unsafe types, Solhint findings) blocks the commit.

/** @type {import("lint-staged").Configuration} */
export default {
  // TypeScript / JavaScript: ESLint (typed rules + TSDoc) with autofix, then Prettier.
  "*.{ts,tsx,js,mjs,cjs}": ["eslint --fix --max-warnings=0 --no-warn-ignored", "prettier --write"],

  // Production Solidity: Prettier, then Solhint (NatSpec, security and style rules).
  "contracts/src/**/*.sol": [
    "prettier --write",
    "solhint --config contracts/.solhint.json --disc --noPoster --max-warnings 0",
  ],

  // Solidity tests: formatting only (test functions do not need NatSpec).
  "contracts/test/**/*.sol": "prettier --write",

  // Config, docs and styles.
  "*.{json,md,yml,yaml,css,html}": "prettier --write",

  // Python pipeline: ruff formatter and linter (incl. docstring rules) from the uv environment.
  "pipeline/**/*.py": [
    "uv run --project pipeline ruff format",
    "uv run --project pipeline ruff check --fix",
  ],
};
