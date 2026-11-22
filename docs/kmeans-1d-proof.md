# Proof of exact 1-D k-means

`kmeans_1d` and `OptimalDiscretizer` find a global minimum of the k-means objective for each feature. A Lean 4 proof
with Mathlib checks this claim for the compiled kernel `optimal_starts`. This page states what the proof shows, what it
does not show, and how to check it.

<p><a href="proofs/kmeans-1d.pdf">Read the paper (PDF)</a></p>

## What is proved

For sorted values $x_0 \le \dots \le x_{n-1}$ and $1 \le k \le n$, in exact arithmetic:

- **Global optimum.** The partition of `optimal_starts` costs no more than the k-means objective
  $\sum_i (x_i - \mu_{\ell(i)})^2$ of any clustering into $k$ clusters, with any labels $\ell$ and any centers $\mu$
  (`codeStarts_le_clusterCost`).
- **Contiguity.** Each clustering has a clustering with contiguous clusters and the same centers that costs no more
  (`exists_contiguous_le`).
- **Dynamic program.** The layers of the dynamic program give the smallest cost of a partition into contiguous,
  non-empty intervals, and the walk back of the code reaches it (`layer_isLeast`, `backtrack_spec`).
- **Total monotonicity.** The matrix that the code searches in each layer is totally monotone, by the quadrangle
  inequality of the squared error of sorted values (`layerMatrix_totallyMonotone`, `cost_quadrangle`).
- **SMAWK.** SMAWK, as the code implements it, returns the leftmost minimum of each row: a tie goes to the leftmost
  column (`smawk_isLeftmostMin`).
- **The code.** The prefix-sum formula of the code is the squared error (`codeCost_eq_cost`), and the arrays of the
  code hold the layers of the model (`codeLayer_eq_layer`).

## What is not proved

- Floating point. The model uses real numbers, and the code uses doubles. Rounding can make SMAWK pick a column whose
  cost is a little above the minimum. The unit tests compare the result with a plain dynamic program and with a search
  over every clustering, with a relative tolerance of $10^{-9}$.
- The Python wrapper: the sort, the labels and the centroids of `kmeans_1d`. The unit tests cover them.
- The run time and the memory. The unit tests measure them on $10^6$ values.
- The choice of the number of bins by a scorer. The scorers are heuristics, and no claim of optimality covers them.

## Check the proof

The Lean files are in
[`proofs/OptimalDiscretizerProofs/KMeans1D/`](https://github.com/johnny-godoy/optimal-discretizer/tree/main/proofs/OptimalDiscretizerProofs/KMeans1D),
and the Typst source of the paper is
[`proofs/papers/kmeans-1d/paper.typ`](https://github.com/johnny-godoy/optimal-discretizer/blob/main/proofs/papers/kmeans-1d/paper.typ).
Run `lake exe cache get` and then `lake build` in `proofs/`. The build must end with
`Build completed successfully`, and each `#print axioms` line must list only `propext`, `Classical.choice` and
`Quot.sound`. The workflow `proofs.yml` runs the same check in CI.

<p><a href="proofs/kmeans-1d.pdf">Open the paper (PDF) in its own page</a></p>

<iframe src="proofs/kmeans-1d.pdf" title="Exact 1-D k-Means by SMAWK" width="100%" height="900"></iframe>
