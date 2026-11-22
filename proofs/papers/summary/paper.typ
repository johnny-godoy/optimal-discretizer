// Paper: the mean of the summary statistics lies between the minimum and the maximum.
// The docs build compiles it into docs/proofs/summary.pdf, with papers/ as the root.

#import "/style.typ": *
#show: paper.with(title: "Bounds of the Mean of a Summary")

#align(center)[
  #text(size: 17pt, weight: "bold")[Bounds of the Mean of a Summary]
  #v(0.4em)
  #text(size: 11pt)[A proof checked in Lean 4]
]

#v(1em)

*Summary.* The function `summarize` of `src/optimal_discretizer/domain/summary.py` returns the count, the minimum, the
maximum and the mean of a sequence of numbers. This paper proves that the mean lies between the minimum and the
maximum. A Lean 4 file @lean4 checks every statement. The topic is the example that a new topic copies.

= Claims and scope <sec-claims>

*Claim 1.* For a nonempty sequence, the mean that `summarize` returns is at least the minimum and at most the maximum.

The proof covers exact arithmetic on natural numbers. @sec-limits lists what it does not cover.

= Model <sec-model>

#table(
  columns: (auto, 1fr, 1fr),
  stroke: 0.4pt + luma(160),
  inset: 5pt,
  [*Symbol*], [*Meaning*], [*Code*],
  [$x_1, ..., x_n$], [The values, with $n >= 1$.], [`values` in `summarize`],
  [$n$], [The count.], [`len(values)`],
  [$S$], [The sum $x_1 + ... + x_n$.], [`sum(values)`],
  [$a, b$], [A lower and an upper bound of every value.], [`min(values)`, `max(values)`],
)

The mean is $S / n$. The minimum $a$ and the maximum $b$ satisfy $a <= x_i <= b$ for each $i$, by their definition.

= Result <sec-result>

#theorem("bounds of a sum", lean: ("OptimalDiscretizerProofs/Summary/Bounds.lean", "mean_between"))[
  If $a <= x_i <= b$ for each $i$, then $a n <= S <= b n$.
]

#proof[
  #step(1, 1)[_The lower bound $a n <= S$ holds._ By induction on $n$. For $n = 0$ both sides are $0$. A new value
    $x >= a$ adds $a$ to the left side and $x$ to the right side (`lower_bound`).]
  #step(1, 2)[_The upper bound $S <= b n$ holds._ By the same induction (`upper_bound`).]
  #step(1, 3)[#qed[steps 1 and 2]]
]

#corollary("Claim 1")[
  If $n >= 1$, then $a <= S / n <= b$.
]

#proof[
  Divide the inequalities of the theorem by $n > 0$.
]

= Limits <sec-limits>

- The model uses natural numbers. The code uses floating point, where a sum rounds. A claim about rounding is out of
  scope.
- The division by $n$ of the corollary is a step on paper, outside the Lean check.

= Computer check <sec-check>

`just proofs` runs `lake build` in `proofs/`. The build ends with `Build completed successfully`, and the axiom check
of `OptimalDiscretizerProofs/Summary/Axioms.lean` lists only `propext` and `Quot.sound`.

#bibliography("references.yml", title: "References")

#pagebreak()

= Appendix: statements and theorems <sec-appendix>

The proof is checked at the commit that adds this topic, with the Lean release of `proofs/lean-toolchain`.

#table(
  columns: (auto, 1fr),
  stroke: 0.4pt + luma(160),
  inset: 5pt,
  [*Statement*], [*Lean theorem*],
  [Theorem 1], [`OptimalDiscretizerProofs.Summary.Bounds.mean_between`],
  [Step 1], [`OptimalDiscretizerProofs.Summary.Bounds.lower_bound`],
  [Step 2], [`OptimalDiscretizerProofs.Summary.Bounds.upper_bound`],
)
