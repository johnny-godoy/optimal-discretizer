import Mathlib

/-!
# The cost of an interval of sorted values

`x : ℕ → ℝ` holds the sorted values; only the indices below `n` matter, and the model extends them by any monotone
continuation. An interval is a half-open range `[a, e)` of indices; the code's interval `first .. last` (both
included) is `[first, last + 1)`.

* `cost x a e` is the sum of squared deviations from the mean of the interval.
* `cost_le_sum_sq_sub` says that the mean is the best center: any other center gives at least this cost.
* `codeCost_eq_cost` says that the code's formula, from prefix sums of values that are shifted by a center, gives the
  same number, so `interval_cost` of `optimal_partition.pyx` computes `cost` in exact arithmetic.
* `cost_quadrangle` is the quadrangle inequality of the cost of sorted values, from which the total monotonicity of
  the matrix of each layer follows.
-/

namespace OptimalDiscretizerProofs.KMeans1D.Cost

open Finset

/-- The mean of the values of `[a, e)`. -/
noncomputable def mean (x : ℕ → ℝ) (a e : ℕ) : ℝ := (∑ t ∈ Ico a e, x t) / (e - a : ℕ)

/-- The sum of squared deviations from the mean of `[a, e)`. -/
noncomputable def cost (x : ℕ → ℝ) (a e : ℕ) : ℝ := ∑ t ∈ Ico a e, (x t - mean x a e) ^ 2

theorem sum_sub_mean (x : ℕ → ℝ) {a e : ℕ} (hae : a < e) : ∑ t ∈ Ico a e, (x t - mean x a e) = 0 := by
  have hpos : ((e - a : ℕ) : ℝ) ≠ 0 := by exact_mod_cast (Nat.sub_pos_of_lt hae).ne'
  rw [sum_sub_distrib, sum_const, Nat.card_Ico, nsmul_eq_mul, mean]
  field_simp
  ring

/-- The cost around a center `center` is the cost around the mean plus the length times the squared distance of the
two centers. -/
theorem sum_sq_sub_eq (x : ℕ → ℝ) {a e : ℕ} (hae : a < e) (center : ℝ) :
    ∑ t ∈ Ico a e, (x t - center) ^ 2 = cost x a e + (e - a : ℕ) * (mean x a e - center) ^ 2 := by
  have h : ∀ t, (x t - center) ^ 2 =
      (x t - mean x a e) ^ 2 + 2 * (mean x a e - center) * (x t - mean x a e) + (mean x a e - center) ^ 2 := by
    intro t; ring
  simp_rw [h, sum_add_distrib, ← mul_sum, sum_sub_mean x hae, sum_const, Nat.card_Ico, nsmul_eq_mul, cost]
  ring

/-- The mean is the best center of an interval. -/
theorem cost_le_sum_sq_sub (x : ℕ → ℝ) {a e : ℕ} (hae : a < e) (center : ℝ) :
    cost x a e ≤ ∑ t ∈ Ico a e, (x t - center) ^ 2 := by
  rw [sum_sq_sub_eq x hae center]
  have : (0 : ℝ) ≤ (e - a : ℕ) * (mean x a e - center) ^ 2 := by positivity
  linarith

theorem cost_nonneg (x : ℕ → ℝ) (a e : ℕ) : 0 ≤ cost x a e := sum_nonneg fun _ _ => sq_nonneg _

/-- The mean of a non-empty interval of sorted values lies between its first and its last value. -/
theorem mean_mem (x : ℕ → ℝ) (hx : Monotone x) {a e : ℕ} (hae : a < e) :
    x a ≤ mean x a e ∧ mean x a e ≤ x (e - 1) := by
  have hpos : (0 : ℝ) < (e - a : ℕ) := by exact_mod_cast Nat.sub_pos_of_lt hae
  have hlow : (e - a : ℕ) * x a ≤ ∑ t ∈ Ico a e, x t := by
    have := sum_le_sum (s := Ico a e) (f := fun _ => x a) (g := x) (fun t ht => hx (mem_Ico.1 ht).1)
    simpa [sum_const, Nat.card_Ico, nsmul_eq_mul] using this
  have hhigh : ∑ t ∈ Ico a e, x t ≤ (e - a : ℕ) * x (e - 1) := by
    have := sum_le_sum (s := Ico a e) (f := x) (g := fun _ => x (e - 1))
      (fun t ht => hx (Nat.le_sub_one_of_lt (mem_Ico.1 ht).2))
    simpa [sum_const, Nat.card_Ico, nsmul_eq_mul] using this
  refine ⟨?_, ?_⟩
  · rw [mean, le_div_iff₀ hpos]; linarith
  · rw [mean, div_le_iff₀ hpos]; linarith

/-- If every value of a range lies on the same side of two centers, the nearer center gives the smaller sum. -/
theorem sum_sq_le_of_side (x : ℕ → ℝ) (s : Finset ℕ) {near far : ℝ}
    (hside : ∀ t ∈ s, (far ≤ near ∧ near ≤ x t) ∨ (x t ≤ near ∧ near ≤ far)) :
    ∑ t ∈ s, (x t - near) ^ 2 ≤ ∑ t ∈ s, (x t - far) ^ 2 := by
  apply sum_le_sum
  intro t ht
  rcases hside t ht with ⟨h1, h2⟩ | ⟨h1, h2⟩ <;> nlinarith

/-- **The quadrangle inequality.** For sorted values and `a < b < c < d`, the cost of `[a, c)` plus that of `[b, d)`
is at most the cost of `[a, d)` plus that of `[b, c)`. -/
theorem cost_quadrangle (x : ℕ → ℝ) (hx : Monotone x) {a b c d : ℕ} (hab : a < b) (hbc : b < c) (hcd : c < d) :
    cost x a c + cost x b d ≤ cost x a d + cost x b c := by
  set outer := mean x a d
  set inner := mean x b c
  have hinner := mean_mem x hx hbc
  have hsplit_ad : ∑ t ∈ Ico a d, (x t - outer) ^ 2 =
      ∑ t ∈ Ico a b, (x t - outer) ^ 2 + ∑ t ∈ Ico b c, (x t - outer) ^ 2 + ∑ t ∈ Ico c d, (x t - outer) ^ 2 := by
    rw [sum_Ico_consecutive _ hab.le hbc.le, sum_Ico_consecutive _ (hab.trans hbc).le hcd.le]
  have hsplit_ac (center : ℝ) : ∑ t ∈ Ico a c, (x t - center) ^ 2 =
      ∑ t ∈ Ico a b, (x t - center) ^ 2 + ∑ t ∈ Ico b c, (x t - center) ^ 2 :=
    (sum_Ico_consecutive _ hab.le hbc.le).symm
  have hsplit_bd (center : ℝ) : ∑ t ∈ Ico b d, (x t - center) ^ 2 =
      ∑ t ∈ Ico b c, (x t - center) ^ 2 + ∑ t ∈ Ico c d, (x t - center) ^ 2 :=
    (sum_Ico_consecutive _ hbc.le hcd.le).symm
  have hcost_ad : cost x a d = ∑ t ∈ Ico a d, (x t - outer) ^ 2 := rfl
  have hcost_bc : cost x b c = ∑ t ∈ Ico b c, (x t - inner) ^ 2 := rfl
  rcases le_total outer inner with hle | hle
  · -- the values right of c are above the inner mean, which is above the outer mean
    have hright : ∑ t ∈ Ico c d, (x t - inner) ^ 2 ≤ ∑ t ∈ Ico c d, (x t - outer) ^ 2 := by
      apply sum_sq_le_of_side
      intro t ht
      left
      exact ⟨hle, le_trans hinner.2 (hx (by have := (mem_Ico.1 ht).1; omega))⟩
    have h1 := cost_le_sum_sq_sub x (hab.trans hbc) outer
    have h2 := cost_le_sum_sq_sub x (hbc.trans hcd) inner
    rw [hsplit_ac] at h1
    rw [hsplit_bd] at h2
    rw [hcost_ad, hcost_bc, hsplit_ad]
    linarith
  · -- the values left of b are below the inner mean, which is below the outer mean
    have hleft : ∑ t ∈ Ico a b, (x t - inner) ^ 2 ≤ ∑ t ∈ Ico a b, (x t - outer) ^ 2 := by
      apply sum_sq_le_of_side
      intro t ht
      right
      exact ⟨le_trans (hx (le_of_lt (mem_Ico.1 ht).2)) hinner.1, hle⟩
    have h1 := cost_le_sum_sq_sub x (hab.trans hbc) inner
    have h2 := cost_le_sum_sq_sub x (hbc.trans hcd) outer
    rw [hsplit_ac] at h1
    rw [hsplit_bd] at h2
    rw [hcost_ad, hcost_bc, hsplit_ad]
    linarith

/-! ## The formula of the code -/

/-- The prefix sum `sums[e]` of the code, of the values shifted by `center`. -/
noncomputable def prefixSum (x : ℕ → ℝ) (center : ℝ) (e : ℕ) : ℝ := ∑ t ∈ range e, (x t - center)

/-- The prefix sum `squares[e]` of the code. -/
noncomputable def prefixSquares (x : ℕ → ℝ) (center : ℝ) (e : ℕ) : ℝ := ∑ t ∈ range e, (x t - center) ^ 2

/-- `interval_cost(sums, squares, first, last)` of the code, for `a = first` and `e = last + 1`:
`squares[e] - squares[a] - total * total / count`, clamped below at 0. -/
noncomputable def codeCost (x : ℕ → ℝ) (center : ℝ) (a e : ℕ) : ℝ :=
  max ((prefixSquares x center e - prefixSquares x center a) -
    (prefixSum x center e - prefixSum x center a) ^ 2 / (e - a : ℕ)) 0

/-- The formula of the code gives the cost of the interval, whatever the center. -/
theorem codeCost_eq_cost (x : ℕ → ℝ) (center : ℝ) {a e : ℕ} (hae : a < e) :
    codeCost x center a e = cost x a e := by
  have hpos : ((e - a : ℕ) : ℝ) ≠ 0 := by exact_mod_cast (Nat.sub_pos_of_lt hae).ne'
  have hsq : prefixSquares x center e - prefixSquares x center a = ∑ t ∈ Ico a e, (x t - center) ^ 2 := by
    rw [prefixSquares, prefixSquares, sum_Ico_eq_sub _ hae.le]
  have hsum : prefixSum x center e - prefixSum x center a = (e - a : ℕ) * (mean x a e - center) := by
    rw [prefixSum, prefixSum, ← sum_Ico_eq_sub _ hae.le, sum_sub_distrib, sum_const, Nat.card_Ico,
      nsmul_eq_mul, mean]
    field_simp
  have hinner : (prefixSquares x center e - prefixSquares x center a) -
      (prefixSum x center e - prefixSum x center a) ^ 2 / (e - a : ℕ) = cost x a e := by
    rw [hsq, hsum, sum_sq_sub_eq x hae center]
    field_simp
    ring
  rw [codeCost, hinner]
  exact max_eq_left (cost_nonneg x a e)

end OptimalDiscretizerProofs.KMeans1D.Cost
