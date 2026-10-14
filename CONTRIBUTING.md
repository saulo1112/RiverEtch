# Contributing

Conventions for this repository. It is a solo hackathon project, so they are deliberately light,
but they are enforced by tooling wherever possible.

## Language: English only

Everything committed to the repository is written in English: code, identifiers, comments,
docstrings, documentation, commit messages, branch names, pull requests and issues. Conversations
about the project can happen in any language.

## Commit messages: Conventional Commits

Follow [Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/):

```text
<type>(<optional scope>): <summary>

<optional body: what changed and, above all, why>

<optional footers, e.g. BREAKING CHANGE: ...>
```

| Type       | Use it for                                              |
| ---------- | ------------------------------------------------------- |
| `feat`     | A new user-facing capability                            |
| `fix`      | A bug fix                                               |
| `docs`     | Documentation only                                      |
| `test`     | Adding or fixing tests                                  |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf`     | Performance improvement                                 |
| `style`    | Formatting only, no behaviour change                    |
| `build`    | Tooling, dependencies, build scripts                    |
| `ci`       | GitHub Actions workflows                                |
| `chore`    | Anything else that does not touch shipped code          |
| `revert`   | Reverting a previous commit                             |

Scopes: `contracts`, `circuits`, `web`, `pipeline`, `docs`, `ci`, `deps`, `repo`.

Rules: imperative mood ("add", not "added"), lower-case summary, no trailing period, at most
72 characters. Mark breaking changes with `!` after the type/scope and a `BREAKING CHANGE:` footer.

```text
feat(pipeline): seal water-temperature records with their own ledger
fix(web): keep the case view alive when leaving compare mode
docs: explain the trusted setup assumptions
build(deps): bump hardhat to 3.19
```

## Branches

- `main` is always green: CI passes on every commit.
- Work on short-lived branches named `<type>/<short-topic>`, using the commit types above, e.g.
  `feat/compliance-circuit`, `fix/proof-calldata`, `docs/architecture`.
- Merge into `main` through a pull request once CI is green (squash merge keeps one Conventional
  Commit per change).

## Documentation standards

Every public API is documented, and the linters fail when documentation is missing.

| Language   | Standard                | Required on                                                                                                                                                                                                                | Enforced by                   |
| ---------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| Solidity   | NatSpec                 | Contracts, interfaces and libraries: `@title`, `@notice`. Public/external functions: `@notice`, one `@param` per parameter, one `@return` per return value. Events: `@notice`, `@param`. Public state variables: `@notice` | Solhint `use-natspec` (error) |
| TypeScript | TSDoc                   | Exported functions, React components, classes and methods: a description, `@param name - description`, `@returns`                                                                                                          | ESLint `eslint-plugin-jsdoc`  |
| Python     | Google-style docstrings | Public modules, classes, functions and methods                                                                                                                                                                             | ruff `D` (pydocstyle) rules   |
| circom     | Comments                | Each template: what it proves, which inputs are private or public                                                                                                                                                          | Review only                   |

Details:

- **Solidity return values must be named** (`returns (bool isSet)`), so that Solhint can check
  that each one has a matching `@return` tag. `@dev` is welcome for implementation notes.
  Solidity tests (`contracts/test/**`) are exempt from NatSpec.
- **TypeScript**: document React props on the props interface instead of with `@param props.x`.
  Leave out JSDoc types (`{string}`), since TypeScript already provides them.
- **Python**: tests are exempt from docstring rules; type hints are mandatory (`mypy --strict`).

## Pre-commit hook

`npm install` installs a Husky pre-commit hook that runs [lint-staged](lint-staged.config.js) on
staged files only, so it stays fast and never runs the test suites:

- TypeScript/JavaScript: ESLint with `--fix`, then Prettier.
- Solidity in `contracts/src`: Prettier, then Solhint.
- Solidity tests: Prettier only. JSON, Markdown, YAML, CSS and HTML: Prettier only.
- Python: `ruff format` and `ruff check --fix`.

Formatting problems are fixed and re-staged automatically. Anything that cannot be fixed
automatically, such as missing documentation, unsafe types or Solhint findings, **blocks the
commit**: fix it and commit again. Use `git commit --no-verify` only in a real emergency, since CI
runs the same checks anyway.

## Before you push

```bash
npm run check            # what CI runs for contracts, circuits and web
npm run pipeline:check   # what CI runs for the Python pipeline
```

Typed lint rules for the contracts tests rely on generated TypeChain bindings. After a fresh
clone, run `npm run zk:build && npm run compile` once.

## Generated files and secrets

- Never edit generated files. `contracts/src/generated/` (Solidity verifiers),
  `contracts/types/` (TypeChain), `contracts/build/` (circuit artifacts) and `web/dist/` are
  rebuilt by the scripts and are not committed.
- Never commit secrets. `.env*` files are ignored except the `.env.example` templates. For
  deployment keys, prefer `npx hardhat keystore set <NAME>` (encrypted) over environment
  variables.

## Adding a circuit

See [docs/zk-circuits.md](docs/zk-circuits.md#adding-a-circuit).
