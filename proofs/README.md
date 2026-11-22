# Proofs

This directory holds the Lean 4 proofs of the exact mathematical claims of optimal-discretizer, and one paper for each
topic. A claim in the code or the docs that says "optimal", "minimal" or "exact" must have a proof here. The rules for
this directory are in `.claude/rules/proofs.md`.

## Topics

| Topic | Claim | Lean | Paper |
| --- | --- | --- | --- |
| `Summary` | The mean of `summarize` lies between its minimum and its maximum, in exact arithmetic. | `OptimalDiscretizerProofs/Summary/` | `papers/summary/paper.typ` |

## Layout

- `lakefile.toml`, `lean-toolchain` and `lake-manifest.json` pin one Lean release for all topics. A topic that needs
  Mathlib adds it to `lakefile.toml`, pinned to the release that matches `lean-toolchain`.
- `OptimalDiscretizerProofs/<Topic>/` holds the Lean files of a topic, with `Axioms.lean`, which prints the axioms of the main
  theorems.
- `OptimalDiscretizerProofs.lean` imports every topic file.
- `papers/style.typ` is the Typst style that all papers share. `papers/<topic>/paper.typ` is the paper of a topic.

CI runs `lake build` when the Lean files or the pins change (`.github/workflows/proofs.yml`).

## Check the proofs

Install [elan](https://github.com/leanprover/elan), the Lean version manager. Then run `just proofs`. The build must
end with `Build completed successfully`. Each `#print axioms` line may list only `propext`, `Classical.choice` and
`Quot.sound`.

## Build a paper

Run `just docs`. The docs build compiles each `papers/<topic>/paper.typ` into `docs/proofs/<topic>.pdf`.

## Add a topic

1. Add `OptimalDiscretizerProofs/<Topic>/` with the Lean files, and one `import` for each file in `OptimalDiscretizerProofs.lean`.
2. Add `papers/<topic>/paper.typ` and `references.yml`. Start with `#import "/style.typ": *`.
3. Add a row to the table above, and a docs page `docs/<topic>-proof.md`.
