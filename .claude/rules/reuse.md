# Reuse before you create

Agents that work alone and in parallel tend to write a new contract when a fitting one exists. Two contracts for one job
then drift apart, and a reviewer cannot tell which one is canonical. So search first, reuse when the layers allow it, and
register a shared contract in the same change that adds it. Tools check the structural facts. The reviewer checks the
reasons.

## Before you add a shared abstraction

A shared abstraction is a new public `Protocol`, `ABC`, service, adapter interface, or helper that more than one module
uses.

1. Search the registry and the public symbols: `uv run python -m scripts.check_abstractions --search <words>`. Try
   two or three words for the job (`graph text render`). The search is lexical. A search with no hit does not prove that
   no equivalent exists, so read the modules of the owner layer too.
2. Read each candidate. Prefer an existing contract that your layer may import (`architecture.md`, "Layers"). The output of
   the search says which layers may import a hit.
3. If no candidate fits, write the reason in the PR section "Abstraction reuse": a different job, a different owner, or
   an import direction that the layers forbid.
4. Put the new contract in the lowest existing layer that all its users may import. Do not add a `common`, `shared` or
   `utils` package.
5. Add the contract to `architecture/abstractions.yml` in the same change, with a new ID, one owner and the canonical
   symbol. Run `uv run python -m scripts.check_abstractions --check`.

Parallel agents: if another branch or agent may add the same contract, ask the user which one owns it. Do not add
sibling contracts. CI checks the merged result, so a second claim on the same ID, symbol or responsibility fails there.

## What needs no entry

- A private helper (a leading underscore) or a class that one module uses. Keep it in the module of its user.
- A `Protocol` that a consumer defines to keep the import direction (`solid.md`, D). It may look like a contract of a
  lower layer. The overlap check reports this as a warning only. If you want the pair on record, add an entry under
  `exceptions` in the registry with the reason.

## The checks

| Check | Command | Fails when |
| --- | --- | --- |
| Registry | `uv run python -m scripts.check_abstractions --check` | An ID is not unique, a symbol or owner is missing, two active entries claim the same symbol or responsibility, or an exception has no reason. |
| Contract overlap | `uv run python -m scripts.check_contract_overlap` | Two registered contracts of one context have identical signatures, or an approved overlap no longer exists. Other overlaps are warnings. |
| New clones | `just clones` | The change adds a copy-paste clone (50 tokens, 5 lines) that `origin/main` lacks. |

- The first two run in `just check`. The third needs the base branch and Node.js, so CI runs it on each pull
  request and you run it by hand.
- Fix the code, not the check. Remove the clone by calling the existing function, or extract it to the layer that all
  users may import. An `exceptions` entry needs a reason of at least four words and names one pair of contracts.
- An entry of the registry has a status. Mark an old entry `deprecated` with `replaced_by`, and do not keep two active
  entries for one job.
- `scripts/check_abstractions.py` and `scripts/check_contract_overlap.py` read the source with `ast`. They never import
  it, so a missing dependency or an import error does not stop them.
