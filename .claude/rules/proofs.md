# Proofs of mathematical claims

An exact mathematical claim in the code, the docs or a prompt needs a machine-checked proof. Words such as "optimal",
"minimal", "exact", "guaranteed" and "equivalent" mark such a claim. Without a proof, the claim is a hope, and a reader
cannot tell it from a fact. `proofs/` holds the proofs. The first topic, `Summary`, is the template for the next ones.

## When to prove

- A new or changed claim of this kind needs a proof in the same change. Ask the user first when the proof looks large.
- If no proof exists yet, remove the strong word, or say in the docstring that the claim is not proved. Do not leave an
  unproved claim in a docstring that sounds proved.
- A claim about floating point, sampling or a library's tie-breaking is out of scope. Write that in the paper limits.

## Layout

One Lake project serves all topics. Add a topic. Do not add a project.

| Path | Content |
| --- | --- |
| `proofs/OptimalDiscretizerProofs/<Topic>/` | The Lean files of the topic: an abstract file that knows nothing about the code, a model file of the code and `Axioms.lean`. |
| `proofs/OptimalDiscretizerProofs.lean` | One `import` per topic file. |
| `proofs/papers/<topic>/paper.typ` | The paper of the topic, with its `references.yml`. |
| `proofs/papers/style.typ` | The shared Typst style. Extend it. Do not copy it into a paper. |

- Name Lean files and namespaces `OptimalDiscretizerProofs.<Topic>.<File>`. Use `UpperCamelCase` for `<Topic>` and `kebab-case` for
  the paper directory.
- Pin Lean in `proofs/lean-toolchain`, and Mathlib, when a topic needs it, in `proofs/lakefile.toml`. Commit
  `proofs/lake-manifest.json`. Change the pin in a change of its own, and rebuild every topic.
- Use no `sorry`, `admit` or new `axiom`. `Axioms.lean` runs `#print axioms` on the main theorems. A main theorem may use
  only `propext`, `Classical.choice` and `Quot.sound`.
- State "the first k with" through hypotheses. Do not use `Nat.find`. The statements then stay close to the code.

## Steps

1. Read the code and write the model from it, line by line. The code wins over any text. If the model differs from the
   docstring or from the request, prove the code and report the difference to the user as an open question. Do not
   change the code to match a proof, unless the user asks.
2. Prove the abstract result first, then apply it in the model file.
3. Write the paper from the template: claims and scope, model with a table from each symbol to the function and expression of the code, the
   abstract result, the application, limits, computer check, references, and an appendix. Cite the Lean name and file
   next to each statement. The appendix has the commit, the versions, the commands from a clean clone, the expected output
   and a table from each statement to its Lean theorem.
   Name functions and expressions of the code. Do not cite line numbers, because they go stale with the next change.
   Do not describe the writing style of the paper inside the paper.
4. Commit the Lean files first. Write that commit in the appendix as the commit that the proof was checked at. Then
   commit the paper. Commit the Typst source only, not a PDF.
5. Point the docstring of the covered code to the paper in one sentence. Add a docs page `docs/<topic>-proof.md` that
   states the claims and links to `proofs/<topic>.pdf`. `scripts/build_docs.py` compiles each
   `proofs/papers/<topic>/paper.typ` into `docs/proofs/<topic>.pdf`. Add the page to the nav in `zensical.toml`.
6. Run `just check`, then `just proofs`, then `just docs`, which compiles the paper.

## Keep the proof true

- When you change code that a paper covers, read its correspondence table. Update the model, the Lean files and the
  appendix, and rebuild. A proof of old code is not a proof of the new code.
- Do not mark a proof as checked without a successful `lake build`. If the network blocks elan or the Mathlib cache,
  read the environment documentation, report the blocked host, and say what you ran instead.
- `.github/workflows/proofs.yml` runs `lake build` and checks the axioms, but only when the Lean files or the pins
  change. A change to the code does not start it, because the proofs do not import the code. The unit tests guard the
  link between the code and the model. The docs build compiles the papers.
- Write the paper by `writing-style.md`: Bourbaki structure, Lamport steps, ASD-STE100 language, one term for one
  concept.
