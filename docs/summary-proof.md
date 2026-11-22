# Proof of the summary bounds

The mean that `summarize` returns lies between the minimum and the maximum. This page states what a proof shows, and
where to read it.

<p><a href="../proofs/summary.pdf">Read the paper (PDF)</a></p>

## What is proved

For values $x_1, ..., x_n$ with bounds $a \le x_i \le b$, the sum $S$ satisfies $a n \le S \le b n$. With $n \ge 1$,
the mean $S / n$ then lies between $a$ and $b$. The Lean theorem is `mean_between` in `proofs/`.

## What is not proved

The model uses exact arithmetic. The code uses floating point, where a sum rounds.
