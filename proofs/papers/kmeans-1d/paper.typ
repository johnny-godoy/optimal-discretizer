// Paper: optimal_starts returns a global minimum of the 1-D k-means objective.
// The docs build compiles it into docs/proofs/kmeans-1d.pdf, with papers/ as the root.

#import "/style.typ": *
#show: paper.with(title: "Exact 1-D k-Means by SMAWK")

#align(center)[
  #text(size: 17pt, weight: "bold")[Exact 1-D k-Means by SMAWK]
  #v(0.4em)
  #text(size: 11pt)[A proof of `optimal_starts`, checked in Lean 4 with Mathlib]
]

#v(1em)

*Summary.* The kernel of the package partitions $n$ sorted values into $k$ contiguous intervals. It is the function
`optimal_starts` of the file `optimal_partition.pyx` in `src/optimal_discretizer/domain/`. It follows the dynamic program of Grønlund et al. @gronlund, and it finds the
minimum of each layer with the SMAWK algorithm @smawk. This paper proves, in exact arithmetic, that the partition costs
no more than any clustering of the values into $k$ clusters. Lean 4 @lean4 and Mathlib @mathlib check every statement.

= Claims and scope <sec-claims>

The values $x_0 <= x_1 <= dots.c <= x_(n-1)$ are sorted, and $1 <= k <= n$.

+ *Contiguity.* For each clustering of the values, some clustering with the same centers and contiguous clusters costs
  no more (Theorem 4).
+ *Dynamic program.* The layers of the dynamic program give the smallest cost of a partition into contiguous,
  non-empty intervals, and the walk back of the code reaches it (Theorem 2).
+ *Total monotonicity.* The matrix that the code searches in each layer is totally monotone (Theorem 5).
+ *SMAWK.* SMAWK, as the code implements it, returns for each row the leftmost column with the smallest entry
  (Theorem 1).
+ *Global optimum.* The partition of the code costs no more than the k-means objective of any clustering into $k$
  clusters, with empty clusters allowed (Theorem 7).

The proof covers exact arithmetic on real numbers. @sec-limits lists what it does not cover.

= Model <sec-model>

An interval is a half-open range $[a, e)$ of indices. The interval `first .. last` of the code, with both ends
included, is $[#raw("first"), #raw("last") + 1)$.

#table(
  columns: (auto, 1fr, 1fr),
  stroke: 0.4pt + luma(160),
  inset: 5pt,
  [*Symbol*], [*Meaning*], [*Code*],
  [$x_i$], [The sorted values.], [`sorted_values[i]`],
  [$w(a, e)$], [The squared error of $[a, e)$ around its mean.], [`interval_cost(sums, squares, a, e - 1)`],
  [$D_m (e)$], [The smallest cost of $[0, e)$ in $m + 1$ intervals, or $infinity$.], [`cost[m][e - 1]`: the arrays
    `previous` and `current`],
  [$C_m (i, j)$], [$D_(m-1) (j) + w(j, i + 1)$ if $j <= i$, else $infinity$.], [`matrix_entry(matrix, i, j)` of layer
    $m$],
  [$R_m$], [The rows and the columns $m, ..., n - 1$ of layer $m$.], [`smawk(&matrix, layer, 1, n - layer, columns,
    ...)`],
  [$s_0 < dots.c < s_(k-1)$], [The starts of the intervals.], [`starts`],
  [$ell, mu$], [The labels and the centers of a clustering.], [`labels`, `centers` of `clusterCost`],
)

The code centers the values on their mean before the prefix sums, and it clamps the cost of an interval at 0. Neither
step changes $w$ in exact arithmetic (Lemma 2).

*How the code differs from Grønlund et al.* The paper @gronlund defines the matrix of a layer on all column indices
and treats the infeasible entries as $infinity$; the code does the same, with plus infinity above the diagonal and the
rows and columns of layer $m$ from $m$ on. The code finds each layer with SMAWK in $O(n)$ evaluations, not with the
$O(n log n)$ divide-and-conquer variant.

= Abstract results <sec-abstract>

== SMAWK <sec-smawk>

The matrix $M : NN times NN -> alpha$ has entries in a linear order. The rows and the columns are increasing lists.

#definition("total monotonicity", lean: ("OptimalDiscretizerProofs/KMeans1D/Smawk.lean", "TotallyMonotone"))[
  $M$ is totally monotone on the rows $R$ and the columns $C$ if, for rows $i < i'$ and columns $j < j'$,
  $M(i, j') < M(i, j)$ implies $M(i', j') < M(i', j)$.
]

#definition("leftmost minimum", lean: ("OptimalDiscretizerProofs/KMeans1D/Smawk.lean", "IsLeftmostMin"))[
  A column $c$ of $S$ is the leftmost minimum of row $r$ if $M(r, c) <= M(r, d)$ for each $d in S$, and
  $M(r, c) < M(r, d)$ for each $d in S$ with $d < c$.
]

The model of SMAWK has three parts. REDUCE (`popWhile`, `reduceStep`, `reduce`) keeps a stack of columns: for each new
column $c$, it pops the top $t$ while $M(r, c) < M(r, t)$ in the row $r$ of the position of $t$, and it pushes $c$ if
the stack has fewer entries than there are rows. The recursion (`smawk`) runs on the rows at the odd positions
(`odds`). INTERPOLATE (`scan`, `interp`) scans the kept columns of each row at an even position, from the current
position to the minimum of the next row, and it replaces the best column only on a strictly smaller entry.

#lemma("REDUCE", lean: ("OptimalDiscretizerProofs/KMeans1D/Smawk.lean", "reduce_spec"))[
  If $M$ is totally monotone on $R times C$, REDUCE returns increasing columns of $C$, at most one for each row, that
  hold the leftmost minimum of each row over $C$.
]

#proof[
  #step(1, 1)[_The stack satisfies an invariant after each column._ Each column of the stack is no better than the
    column below it in each row above its position (`Chain`), the stack has at most $|R|$ entries, and it holds the
    leftmost minimum of each row over the columns so far (`ReduceInv`, `reduceStep_inv`).]
  #step(1, 2)[_A popped column is not a leftmost minimum._ In the rows at or below its position, the new column is
    strictly better, by total monotonicity. In the rows above, the column below it is as good and further left
    (`popWhile_keeps`).]
  #step(1, 3)[_A column that is not pushed is not a leftmost minimum._ The stack is full, and its top is as good in
    the last row, so it is as good in each row and further left.]
  #step(1, 4)[#qed[steps 1 to 3, by induction on the columns (`reduce_fold_inv`)]]
]

#theorem("SMAWK", lean: ("OptimalDiscretizerProofs/KMeans1D/Smawk.lean", "smawk_isLeftmostMin"))[
  If $M$ is totally monotone on the increasing rows $R$ and the increasing, non-empty columns $C$, `smawk` gives each
  row of $R$ its leftmost minimum over $C$.
]

#proof[
  #step(1, 1)[_The recursion is right on the odd rows._ By induction on the number of rows, on the kept columns,
    where total monotonicity still holds.]
  #step(1, 2)[_The leftmost minima do not move left as the row grows_ (`IsLeftmostMin.mono`).]
  #step(1, 3)[_The scan of an even row covers its leftmost minimum._ The scan starts at the minimum of the row above
    and stops at that of the row below, so by step 2 the window holds the minimum (`scan_isLeftmostMin`,
    `interp_spec`).]
  #step(1, 4)[#qed[steps 1 to 3 and Lemma 1, which makes the minimum over the kept columns the minimum over $C$]]
]

== The dynamic program <sec-dp>

The cost of an interval is any function $w$ here. A partition of $[0, e)$ into $p$ intervals is the list of starts of
its intervals, last interval first (`IsPartition`), and its cost is the sum of $w$ over its intervals (`partCost`).

#definition("layers", lean: ("OptimalDiscretizerProofs/KMeans1D/DynamicProgram.lean", "layer"))[
  $D_0 (e) = w(0, e)$ for $e > 0$, and $D_(m+1) (e) = min_(j in [m + 1, e)) D_m (j) + w(j, e)$, with
  $infinity$ for an empty minimum.
]

#theorem("dynamic program", lean: ("OptimalDiscretizerProofs/KMeans1D/DynamicProgram.lean", "layer_isLeast",
  "backtrack_spec"))[
  If $m < e$, $D_m (e)$ is the smallest cost of a partition of $[0, e)$ into $m + 1$ non-empty, contiguous intervals.
  If each choice is a column with the smallest sum, the walk back gives such a partition with the cost $D_m (e)$.
]

#proof[
  #step(1, 1)[_No partition costs less._ By induction on $m$: the last interval starts at a column of the minimum,
    and the rest is a partition into $m$ intervals (`layer_le_partCost`).]
  #step(1, 2)[_The walk back reaches the bound._ By induction on $m$ (`backtrack_spec`).]
  #step(1, 3)[#qed[steps 1 and 2]]
]

== The cost of sorted values <sec-cost>

#lemma("the formula of the code", lean: ("OptimalDiscretizerProofs/KMeans1D/Cost.lean", "codeCost_eq_cost"))[
  For each center $c$, $max(0, sum (x_t - c)^2 - (sum (x_t - c))^2 \/ (e - a)) = w(a, e)$, with both sums over
  $[a, e)$.
]

#theorem("quadrangle inequality", lean: ("OptimalDiscretizerProofs/KMeans1D/Cost.lean", "cost_quadrangle"))[
  For sorted values and $a < b < c < d$, $w(a, c) + w(b, d) <= w(a, d) + w(b, c)$.
]

#proof[
  #step(1, 1)[_The mean is the best center_ (`cost_le_sum_sq_sub`). Let $mu$ be the mean of $[a, d)$ and $nu$ that of
    $[b, c)$, with $x_b <= nu <= x_(c-1)$ (`mean_mem`).]
  #step(1, 2)[_Case $mu <= nu$._ Use $mu$ for $[a, c)$ and $nu$ for $[b, d)$. The values of $[c, d)$ are at least
    $nu$, so $nu$ is nearer to each of them than $mu$.]
  #step(1, 3)[_Case $nu <= mu$._ Use $nu$ for $[a, c)$ and $mu$ for $[b, d)$. The values of $[a, b)$ are at most
    $nu$, so $nu$ is nearer to each of them than $mu$.]
  #step(1, 4)[#qed[steps 1 to 3, after the sums are split at $b$ and $c$]]
]

== Contiguity <sec-contiguity>

#theorem("contiguity", lean: ("OptimalDiscretizerProofs/KMeans1D/Contiguity.lean", "exists_contiguous_le"))[
  For sorted values, labels $ell$ and centers $mu$, a permutation $sigma$ of the values exists such that the clusters
  of $ell compose sigma$ are runs of consecutive values, the centers $mu compose ell compose sigma$ increase, and
  $sum_i (x_i - mu_(ell(sigma(i))))^2 <= sum_i (x_i - mu_(ell(i)))^2$.
]

#proof[
  #step(1, 1)[_Sort the values by the key $(mu_(ell(i)), ell(i))$ in lexicographic order._ Equal labels have equal
    keys, so each cluster is a run.]
  #step(1, 2)[_The cost does not grow._ The cost is $sum x_i^2 - 2 sum x_i nu_i + sum nu_i^2$ for the assigned centers
    $nu$. The last sum does not change under a permutation, and the middle sum is largest when $x$ and $nu$ are sorted
    the same way, by the rearrangement inequality (`clusterCost_comp_le`).]
  #step(1, 3)[#qed[steps 1 and 2]]
]

= Application to the code <sec-application>

#theorem("total monotonicity", lean: ("OptimalDiscretizerProofs/KMeans1D/Model.lean",
  "layerMatrix_totallyMonotone"))[
  For sorted values, the matrix $C_m$ of each layer is totally monotone, on every set of rows and columns.
]

#proof[
  If $C_m (i, j') < C_m (i, j)$ with $j < j'$, the left entry is finite, so $j' <= i$. If $C_m (i', j)$ is infinite,
  the claim holds. Otherwise all four entries are finite, and the quadrangle inequality with $a = j$, $b = j'$,
  $c = i + 1$, $d = i' + 1$ gives the claim.
]

#theorem("the arrays of the code", lean: ("OptimalDiscretizerProofs/KMeans1D/Model.lean", "codeLayer_eq_layer",
  "optimal_starts_isLeast"))[
  The arrays that `optimal_starts` fills hold $D_m (e)$ for $m < e <= n$. The starts that it writes form a partition
  into $k$ non-empty, contiguous intervals with the cost $D_(k-1) (n)$, the value that it returns, and no such
  partition costs less.
]

#proof[
  By induction on the layers. If the array of layer $m$ holds $D_m$, the matrix of the code agrees with $C_m$ on its
  rows and columns, so SMAWK returns the same leftmost minima (Theorem 1, Theorem 5), and its entries are $D_(m+1)$
  (`smawk_choice_spec`, `codeSmawk_eq`). The walk back with these columns is optimal by Theorem 2.
]

#theorem("global optimum", lean: ("OptimalDiscretizerProofs/KMeans1D/Optimality.lean",
  "codeStarts_le_clusterCost"))[
  Let the values be sorted, and let $1 <= k <= n$. The cost of the partition of `optimal_starts` is at most
  $sum_i (x_i - mu_(ell(i)))^2$ for all labels $ell : {0, ..., n - 1} -> {0, ..., k - 1}$ and centers $mu$.
]

#proof[
  #step(1, 1)[_Make the clustering contiguous_ (Theorem 4). Its centers along the values increase and take at
    most $k$ values.]
  #step(1, 2)[_An increasing assignment of at most $m + 1$ centers to $[0, e)$ costs at least $D_m (e)$._ The last
    run of equal centers costs at least the cost of its interval. The prefix before it has fewer centers: if it is
    long, the induction hypothesis bounds it; if it is short, one interval for each value costs nothing
    (`sum_sq_ge_layer`).]
  #step(1, 3)[_More intervals do not cost more_ (`layer_antitone`), because a split interval costs no more
    (`cost_split`).]
  #step(1, 4)[#qed[steps 1 to 3 and the theorem on the arrays of the code]]
]

The Python wrapper `kmeans_1d` sorts the values, calls `optimal_starts`, and returns the mean of each interval as its
centroid. The mean is the best center of an interval, so the labels and centroids of `kmeans_1d` reach the bound of
Theorem 7. The wrapper is not in the Lean model; the unit tests of `tests/unit/optimal_discretizer/domain/` compare
it with a plain $O(k n^2)$ dynamic program and with a search over every clustering.

= Limits <sec-limits>

- *Floating point is out of scope.* The model uses real numbers. The code computes with doubles: the prefix sums
  round, and two costs that are equal in exact arithmetic can compare as unequal. Then SMAWK can return a column
  whose cost is a little above the minimum, and a tie can go to another column than the leftmost. The centering of
  the values on their mean reduces the cancellation, but no bound on the error is proved. The differential tests
  check the result against direct sums with a relative tolerance of $10^(-9)$.
- *The rows and the columns.* The code walks the rows as the arithmetic progression `first_row + row_step * t`; the
  model uses the list of the same indices.
- *Memory and time.* The proof says nothing about the running time or the memory. The tests check them on $10^6$
  values.
- *The wrapper and the estimator.* The sorting, the labels and the centroids of `kmeans_1d`, the bin edges and the
  scorers of `OptimalDiscretizer` are outside the model. The choice of the number of bins by a scorer is a heuristic,
  and no claim of optimality covers it.
- *The integers of the code.* The indices are `Py_ssize_t`, and the model uses natural numbers without a bound.

= Computer check <sec-check>

`just proofs` runs `lake build` in `proofs/`. `Axioms.lean` prints the axioms of the nine main theorems. Each list
holds only `propext`, `Classical.choice` and `Quot.sound`, and the build reports success. The workflow
`.github/workflows/proofs.yml` runs the same build, and it fails on any other axiom and on `sorry`.

#bibliography("references.yml", title: "References")

#pagebreak()

= Appendix <sec-appendix>

== Versions and commit

The proof is checked at commit `d8c2481` of `johnny-godoy/optimal-discretizer`, with Lean `v4.35.0`
(`proofs/lean-toolchain`) and Mathlib `v4.35.0` (`proofs/lakefile.toml`, `proofs/lake-manifest.json`).

== Commands from a clean clone

```sh
git clone https://github.com/johnny-godoy/optimal-discretizer
cd optimal-discretizer/proofs
lake exe cache get   # download the Mathlib cache; do not build Mathlib from source
lake build
```

The expected output ends with nine lines of the first form below, one for each main theorem, and the last line:

```text
info: OptimalDiscretizerProofs/KMeans1D/Axioms.lean:11:0: '...' depends on axioms:
  [propext, Classical.choice, Quot.sound]
Build completed successfully (9055 jobs).
```

== Statements and theorems

#table(
  columns: (auto, 1fr),
  stroke: 0.4pt + luma(160),
  inset: 5pt,
  [*Statement*], [*Lean theorem (namespace `OptimalDiscretizerProofs.KMeans1D`)*],
  [Lemma 1 (REDUCE)], [`Smawk.reduce_spec`],
  [Theorem 1 (SMAWK)], [`Smawk.smawk_isLeftmostMin`],
  [Theorem 2 (dynamic program)], [`DynamicProgram.layer_isLeast`, `DynamicProgram.backtrack_spec`],
  [Lemma 2 (the formula of the code)], [`Cost.codeCost_eq_cost`],
  [Theorem 3 (quadrangle inequality)], [`Cost.cost_quadrangle`],
  [Theorem 4 (contiguity)], [`Contiguity.exists_contiguous_le`],
  [Theorem 5 (total monotonicity)], [`Model.layerMatrix_totallyMonotone`],
  [Theorem 6 (the arrays of the code)], [`Model.codeLayer_eq_layer`, `Model.optimal_starts_isLeast`],
  [Theorem 7 (global optimum)], [`Optimality.codeStarts_le_clusterCost`],
)
