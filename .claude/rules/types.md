# Type hints

## Inputs abstract, outputs concrete

Give each parameter the most general type that the function body needs, and give each return value the concrete type
that the function builds. The caller then passes any fitting object, and the return value has all the methods that the
caller may use. The runtime type check (`beartype`) enforces the hints, so a hint that is too narrow raises an error
for a valid call.

| Parameter holds | Hint | Not |
| --- | --- | --- |
| Items that the function only reads, in order | `Sequence[T]` | `list[T]` |
| Items that the function loops over once | `Iterable[T]` | `list[T]` |
| Items that the function only tests for membership | `Collection[T]` or `collections.abc.Set[T]` | `set[T]` |
| Key-value pairs that the function only reads | `Mapping[K, V]` | `dict[K, V]` |
| A file system path | `str \| os.PathLike[str]` | `Path` |
| A number | `float` (the numeric tower accepts `int`) | `int \| float` |

- Return `list`, `dict`, `tuple` or `Path`, as built. Do not return `Sequence`, `Mapping` or `Iterable`.
- Use a concrete parameter type only if the body needs its methods (for example `list.append`), and say why in a comment.
- A third-party class with no abstract base (such as a scikit-learn estimator) stays as it is.
- An `attrs` field is both an input and stored state. Give it the abstract type that the class reads.
- Put an `Optional` or union in the hint when the function accepts plain strings for an enum (`Format | str`).

## Check the abstract type in `isinstance`

A run-time type check is a hint that the code reads at run time, so the same rule applies: check against the most
general type that the next lines need. A check of the concrete class rejects a fitting object, as a too narrow hint
does: `isinstance(x, dict)` is false for a `MappingProxyType`, and `isinstance(x, list)` is false for a tuple.

| The next lines need | Check | Not |
| --- | --- | --- |
| Key-value pairs that they only read | `isinstance(x, Mapping)` | `dict` |
| Items in order | `isinstance(x, Sequence)` | `list` |
| Membership tests | `isinstance(x, collections.abc.Set)` | `set`, `frozenset` |

- The same applies to every other form of a type check:

  | Form | Example |
  | --- | --- |
  | Subclass test | `issubclass(cls, dict)` |
  | Exact type | `type(x) is dict`, `type(x) in (dict, list)`, `x.__class__ is dict` |
  | Name of the type | `type(x).__name__ == "dict"` |
  | Hint test of beartype | `is_bearable(x, dict[str, int])`, `die_if_unbearable(x, list[str])` |
  | Class pattern | `case dict():` |

- Prefer `isinstance` to an exact type, because a subclass keeps the promise of its base (`solid.md`, L). Do not
  compare the name of a type: a rename or a subclass breaks the check, and no tool sees it.
- In a `match`, use a mapping pattern (`case {"a": a}:`), which matches any `Mapping`, or a sequence pattern
  (`case [a, b]:`), which matches any `Sequence` except `str`, `bytes` and `bytearray`.
- A library predicate is a type check too (`inspect.isclass`, `attrs.has`, `np.issubdtype`,
  `pd.api.types.is_dict_like`). Use it only where `isinstance` cannot do the check. No guard covers it.
- A `str` is a `Sequence` too. If a string must not count as a sequence, test `str` first.
- `tuple` may stay: the hints of this project use a tuple for a fixed shape, such as an interval `tuple[float, float]`.
- Check the type at the edge, where the value enters `optimal_discretizer`. Inside, the hints and `beartype` give the type. To pick
  the behavior from the type, use a method of the class (`solid.md`, "Tell, don't ask").
- The semgrep rule `optimal-discretizer-isinstance-abstract-type` in `semgrep/rules.yml` enforces this in `src/`. Its
  test is in `semgrep/rules.py`.

## Return an attrs class for named values

A `dict` or a `tuple` of fields hides the names and the types of the fields: a type checker cannot see a wrong key or a
swapped position, and a caller must remember the order. An attrs class has one name and one type for each field, and
`beartype` checks them at run time.

- Return `@attrs.frozen` (or `@attrs.define`) for a fixed set of fields. Do not return `dict[str, ...]`,
  `tuple[A, B, ...]`, `list[dict[...]]` or `list[tuple[...]]`.
- Put a result class in the module that builds it, and give it a docstring. A private helper may return a private class.
- Pass the fields of an attrs class on with `attrs.asdict(x, recurse=False)` where a `**` call needs them.
- A container is right if the structure is the data, not a set of fields: keys that change from call to call, a fragment
  of a JSON object that the caller merges and serializes, or a homogeneous pair such as an interval
  `tuple[float, float]`. Add `# nosemgrep: optimal-discretizer-return-attrs-not-container -- <reason>` to the line above the `def`.
  `tuple[float, ...]` needs no ignore.
- The semgrep rule `optimal-discretizer-return-attrs-not-container` in `semgrep/rules.yml` enforces this in `src/`. Its test is in
  `semgrep/rules.py`.

## Name the type, not `object`

`object` accepts every value, so it checks as little as `Any`: pyrefly lets any value through, and `beartype` checks
nothing at run time. A hint of `object` also hides from the reader what the value is.

- Use a named alias of `optimal_discretizer.core.custom_types` when one fits. Add an alias there when a new kind of value recurs, and create the module for the first one. The
  rule also covers `*args`, `**kwargs` and string annotations.
- Else write the union of the real types (`tuple[float, float] | str` for an interval or its label), or a `Protocol` for an object that
  the code only calls.
- A hint may keep `object` only when the function exists to inspect a value of any type: an attrs validator that
  ignores the instance, or a reader of an untyped record whose callers narrow the value. Add
  `# nosemgrep: optimal-discretizer-no-object-type -- <reason>` on the line of the hint, or on the line above it when the line is
  long. For a one-line `def`, the line above is the line above the `def`.
- A precise hint can expose a test that passes values the code never produces. Fix the test, not the hint.
- The semgrep rule `optimal-discretizer-no-object-type` in `semgrep/rules.yml` enforces this in `src/`. Its test is in
  `semgrep/rules.py`.
