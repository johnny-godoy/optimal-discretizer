# SOLID

Design code to the five SOLID principles. Each rule below has its reason and the way to apply it in this project.
Review a change against them before you finish. If you break one on purpose, write the reason in a comment.

## S: one reason to change

A module, class or function has one job. If the description needs the word "and", split it.

- Why: a unit with two jobs changes for two reasons, and each change risks the other job.
- Apply: keep the computing of a result apart from its rendering as text, and the I/O apart from both. A function
  that reads data, decides and formats the result is three functions.

## O: extend by adding, not by editing

Adding a case (a file format, a user role, a report kind) must not need an edit in a long `if`/`match` chain.

- Why: each edit of working code can break the cases that exist.
- Apply: put the cases in a table (`_FORMATS`) or in one class per case, and look the case up by key. A chain that
  tests the same flag in many places (`if admin:`) is the sign to use classes.

### Tell, don't ask

Tell an object what to do, and let its class decide how. Do not ask for its type and decide in the caller.

- Why: a branch on the type (`if isinstance(x, A): ... elif isinstance(x, B): ...`) is a chain on one value. Each new
  class needs an edit of every such branch, and a missed branch fails only at run time.
- Apply: give the classes a common method, abstract in the base class, and call it (`kind.describe()`). If the package
  does not own the classes, register one function per class with `functools.singledispatch`.
- Every way to ask makes the same branch: `isinstance`, `issubclass`, `type(x) is`, `type(x) in`, `x.__class__`,
  `type(x).__name__`, `hasattr(x, ...)` (a duck check asks too), and a `match` with two or more class patterns.
- A table keyed by type (`HANDLERS[type(x)](x)`) is a hand-made `singledispatch` that ignores subclasses. A
  `try`/`except AttributeError` around a call that some classes lack is a branch that hides in an exception. Use a
  method or `singledispatch` instead. No guard covers these two forms, so look for them in review.
- One check that narrows a union where a value enters the package (a string or a list for one parameter) is not a
  branch on the type. Keep it, and give it a comment if the reason is not clear.
- The semgrep rule `optimal-discretizer-polymorphism-not-type-branches` in `semgrep/rules.yml` enforces this in `src/`.
  If a type branch must stay (a parsed record of an untyped format), add
  `# nosemgrep: optimal-discretizer-polymorphism-not-type-branches -- <reason>` on the line of the first branch.

## L: a subtype keeps the promise of its base

A subclass or a fake works wherever its base works: same argument types, same result type, no new errors.

- Why: callers rely on the base contract and cannot check each subtype.
- Apply: do not narrow a parameter type or raise a new error in an override. A test double must obey the contract of
  the real object, or the test proves nothing.

## I: small interfaces

A function takes only what it uses, and a class exposes only what its callers need.

- Why: a wide dependency couples a unit to things it does not use, so unrelated changes break it.
- Apply: pass the values that the function reads, not a whole configuration object or a `**kwargs` bag that it
  filters later. Keep an abstract base class to a few methods that all subclasses use.

## D: depend on abstractions at the edges

Domain code (`core`, `domain`) must not import I/O or vendor code. The edge code (`adapters`: files, HTTP clients,
the database, the vendor SDKs) depends on the domain, and not the other way round.

- Why: domain code with no vendor import runs in a plain unit test, and a provider change stays at the edge.
- Apply: if domain code needs a service (a clock, a store), take it as a parameter typed by a `Protocol` or a
  `Callable`, and let the edge code pass the real one. Create the dependency in the caller, not inside the function.

## Check

- `architecture.md` lists the layers and the tools that enforce them: import-linter, the layout check and semgrep. They
  cover the mechanical part of S, O, L and D. You judge the rest.
- Ask for each changed unit: what is its one job, what does the next new case edit, and what does it import?
- Do not split code only to satisfy a letter. Three similar lines are better than a class with one user.
