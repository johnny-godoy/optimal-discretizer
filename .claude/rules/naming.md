# Names

A name tells the reader what a value is. A short or symbolic name makes the reader look up the formula or the line
that sets it. A reader of `word_weight` needs no lookup, and a reader of `alpha` does.

- Give each variable, parameter, field, loop variable and lambda argument a name that says what the value is:
  `word_count`, `token_counts`, `covariance_times_counts`.
- Name a coefficient by what it weights: `word_weight`, `byte_weight`, `digit_weight`. Do not use `a`, `b`, `c`, `alpha`,
  `beta` or `gamma`, in code, in tests, in docstrings or in docs.
- Do not use a single letter, and do not use an abbreviation that a new reader must guess (`idx`, `tmp`, `rng`, `val`).
  Write `bin_index`, `random_generator`.
- Keep the exceptions that tools or the language fix: `_` for an unused value, `msg` for the text of an error (ruff
  asks for it), `self` and `cls`, and the names of the parameters of a library that you call by keyword.
- Mathematical notation belongs in the proof papers. The paper has a table from each symbol to the name in the code
  (`proofs.md`). Do not copy the symbol into the code.
- Rename a value if its meaning changes, so that the name stays true.
- No tool enforces this rule yet. Check your own diff before you commit.
