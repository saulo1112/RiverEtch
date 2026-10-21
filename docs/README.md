# Documentation

Where to find each part of RiverEtch. Every figure in these files comes from a committed result or
a chain read, with its source.

| If you want…                                               | Read                                                                                                                   |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| The short path through the project, and how to check it    | [judges.md](judges.md)                                                                                                 |
| Why a reading can be trusted, and what it does not prove   | [trust-model.md](trust-model.md)                                                                                       |
| The results: every river, its error, the failures included | [water-quality/report.md](water-quality/report.md)                                                                     |
| The rules, fixed and anchored before each test ran         | [preregistrations](#preregistrations) below                                                                            |
| How the record is anchored on Ethereum and timestamped     | [anchoring.md](anchoring.md)                                                                                           |
| How the pieces fit (pipeline, ledgers, web)                | [architecture.md](architecture.md)                                                                                     |
| The format of a sealed reading                             | [schema/README.md](schema/README.md) and [observation-record.v2.schema.json](schema/observation-record.v2.schema.json) |
| How the daily run works, and how to release                | [release.md](release.md)                                                                                               |
| The reaches the daily run reads                            | [water-quality/reach/README.md](water-quality/reach/README.md)                                                         |
| Every decision, in order, with its reason                  | [decisions.md](decisions.md)                                                                                           |

## Preregistrations

Each is a file whose SHA-256 is a line of
[`ledgers/frozen-artifacts.jsonl`](ledgers/frozen-artifacts.jsonl), anchored on Ethereum Sepolia
before its test ran; a change is a new file, never an edit.

| File                                                                                               | What it fixed                                                       |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| [water-quality/preregistration.md](water-quality/preregistration.md)                               | The locked test of every gauged river (v5)                          |
| [water-quality/prospective.md](water-quality/prospective.md)                                       | Prospective scoring, rule v1, and the extreme days                  |
| [water-quality/prospective-v2.md](water-quality/prospective-v2.md)                                 | Prospective scoring, rule v2                                        |
| [water-quality/preregistration-transfer.md](water-quality/preregistration-transfer.md)             | The test on rivers the model never saw, and the reach with no gauge |
| [water-quality/preregistration-class-baseline.md](water-quality/preregistration-class-baseline.md) | Always guessing the most common class, beside the model             |
| [water-quality/preregistration-outside-us.md](water-quality/preregistration-outside-us.md)         | The reach outside the tested region (the Fırat at Birecik)          |
| [water-quality/preregistration-four-classes.md](water-quality/preregistration-four-classes.md)     | Four classes for the reaches with no gauge                          |

## History

The project began as a screening of Colombian reaches (Urrá, the Magdalena), which reached no
level; those folders stay because the pipeline still reads their settings and frozen
scenes: [site-screening/](site-screening/), [urra-validation/](urra-validation/) and
[magdalena-validation/](magdalena-validation/). [zk-circuits.md](zk-circuits.md) describes a
zero-knowledge scaffold the product does not use.
